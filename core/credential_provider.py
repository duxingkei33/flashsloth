"""统一扫码登录引擎 + 凭证基础设施

ScanLoginEngine: 统一处理所有扫码类登录方式（QR码、小程序码等）
save_credential / get_credential: 凭证加密存储（基于 platform_accounts.config_json）
verify_credential: 验证凭证是否仍有效

用法:
    from flashsloth.core.credential_provider import ScanLoginEngine
    sess_id = ScanLoginEngine.start_scan_login("bilibili", "https://www.bilibili.com/")
    result = ScanLoginEngine.poll_scan_login(sess_id)
    ScanLoginEngine.close_scan_login(sess_id)
"""

import json
import os
import queue
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from flashsloth.core.credential_crypto import encrypt_config, decrypt_config

# ─── 全局 session 存储 ──────────────────────────────────
_scan_login_sessions: dict[str, dict] = {}
_scan_login_locks: dict[str, threading.Lock] = {}


def _get_scan_lock(session_id: str) -> threading.Lock:
    """获取或创建 session 锁"""
    if session_id not in _scan_login_locks:
        _scan_login_sessions[session_id] = {}  # ensure session exists for lock consistency
        _scan_login_locks[session_id] = threading.Lock()
    return _scan_login_locks[session_id]


# ─── 扫描类型检测 ──────────────────────────────────────

def _detect_scan_type(page) -> str:
    """自动判断页面是什么类型的扫码登录
    
    返回: "qrcode" | "miniprogram" | "qrcode" (默认)
    """
    try:
        # 检查是否有明确的小程序码特征
        miniprogram_selectors = [
            "img[src*='miniprogram' i]",
            "img[src*='mp' i]",
            "img[class*='miniprogram' i]",
            "img[id*='miniprogram' i]",
        ]
        for sel in miniprogram_selectors:
            el = page.query_selector(sel)
            if el and el.is_visible():
                box = el.bounding_box()
                if box and box.get("width", 0) >= 60 and box.get("height", 0) >= 60:
                    return "miniprogram"

        # 检查是否有 QR 码特征
        qr_selectors = [
            "canvas",
            "img[src*='qrcode' i]",
            "img[src*='qr' i]",
            "div[class*='qrcode' i]",
        ]
        for sel in qr_selectors:
            try:
                elements = page.query_selector_all(sel)
                for el in elements:
                    if not el.is_visible():
                        continue
                    box = el.bounding_box()
                    if box and box.get("width", 0) >= 80 and box.get("height", 0) >= 80:
                        return "qrcode"
            except Exception:
                continue

        # 页面标题/URL 特征
        title = (page.title() or "").lower()
        url = page.url.lower()
        if "miniprogram" in title or "miniprogram" in url or "mp" in url.split("/")[-1]:
            return "miniprogram"
        if "qrcode" in title or "qr" in url:
            return "qrcode"
    except Exception:
        pass

    return "qrcode"  # 默认


# ─── 二维码截图校验 ────────────────────────────────────

def _validate_qr_screenshot(base64_img: str) -> dict:
    """校验截图是否为有效的二维码图像
    
    使用 Pillow 做图像级检测（无需系统 zbar 库）：
    1. 大小检测：base64 解码后 ≥ 5KB
    2. 尺寸检测：二维码至少 100x100 像素
    3. 对比度检测：二维码黑白分明，对比度 > 100
    
    Returns:
        dict: {"valid": bool, "reason": str, "image_info": dict}
    """
    import base64
    from PIL import Image
    import io

    info = {}
    if not base64_img:
        return {"valid": False, "reason": "截图数据为空", "image_info": info}

    try:
        raw = base64.b64decode(base64_img)
    except Exception as e:
        return {"valid": False, "reason": f"base64 解码失败: {str(e)[:60]}", "image_info": info}

    info["raw_size_bytes"] = len(raw)

    # 1. 文件大小检测：PNG 数据 ≥ 5KB
    if len(raw) < 5 * 1024:
        return {"valid": False, "reason": f"截图数据过小 ({len(raw)}B < 5KB)", "image_info": info}

    try:
        img = Image.open(io.BytesIO(raw))
    except Exception as e:
        return {"valid": False, "reason": f"图像格式解析失败: {str(e)[:60]}", "image_info": info}

    w, h = img.size
    info["width"] = w
    info["height"] = h

    # 2. 尺寸检测：≥ 100x100
    if w < 100 or h < 100:
        return {"valid": False, "reason": f"二维码截图尺寸不足 ({w}x{h} < 100x100)", "image_info": info}

    # 3. 对比度检测：灰度化后 max-min > 100
    try:
        gray = img.convert("L")
        pixels = list(gray.getdata())
        contrast = max(pixels) - min(pixels)
        info["contrast"] = contrast
        if contrast < 100:
            return {"valid": False, "reason": f"二维码截图对比度不足 ({contrast} < 100)", "image_info": info}
    except Exception as e:
        return {"valid": False, "reason": f"对比度分析失败: {str(e)[:60]}", "image_info": info}

    return {"valid": True, "reason": "ok", "image_info": info}


# ─── 截图扫码元素 ──────────────────────────────────────

def _screenshot_scan_code(page, scan_type: str = "auto") -> dict:
    """查找页面中的 QR 码/小程序码元素并截图
    
    Args:
        page: Playwright page 对象
        scan_type: "qrcode" | "miniprogram" | "auto" (自动检测)
    
    Returns:
        dict: {
            "image": str,          # base64 编码的 PNG 图片
            "found_qrcode": bool,  # True=精确匹配到≥60x60二维码元素；False=降级截图
        }
    """
    import base64

    def _make_qr_result(img_b64: str) -> dict:
        """截图后校验二维码有效性，返回带验证结果的 dict
        
        自动缩放到 400px 以内（保持宽高比）以优化前端显示。
        """
        # 图片尺寸优化：缩放到 400px 以内
        try:
            import base64 as _b64
            from PIL import Image as _Image
            import io as _io
            raw = _b64.b64decode(img_b64)
            img = _Image.open(_io.BytesIO(raw))
            w, h = img.size
            max_dim = 400
            if w > max_dim or h > max_dim:
                img.thumbnail((max_dim, max_dim), 1)  # LANCZOS = 1
                buf = _io.BytesIO()
                img.save(buf, format='PNG')
                img_b64 = _b64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass

        v = _validate_qr_screenshot(img_b64)
        if v["valid"]:
            return {"image": img_b64, "found_qrcode": True}
        return {
            "image": img_b64,
            "found_qrcode": False,
            "validation_error": v["reason"],
        }

    if scan_type == "auto":
        scan_type = _detect_scan_type(page)

    # QR 码选择器
    qr_selectors = [
        "canvas",
        "img[src*='qrcode' i]",
        "img[src*='qr' i]",
        # DIV 容器类型二维码（B站等使用 DIV 渲染二维码）
        "div.login-scan-box",
        "div[class*='login-scan']",
        "div[class*='qrcode-box']",
        "div[class*='qr-code']",
        "div[class*='qrcode']",
    ]
    # 小程序码选择器
    mp_selectors = [
        "img[src*='miniprogram' i]",
        "img[src*='mp' i]",
        "img[class*='miniprogram' i]",
    ]
    # 通用 QR 容器
    container_selectors = [
        '[class*="qr" i]',
        '[id*="qr" i]',
        '[class*="qrcode" i]',
        '[id*="qrcode" i]',
        '[class*="miniprogram" i]',
        '[id*="miniprogram" i]',
    ]

    # 根据 scan_type 选择主要选择器
    primary_selectors = []
    secondary_selectors = []

    if scan_type == "qrcode":
        primary_selectors = qr_selectors
        secondary_selectors = mp_selectors
    elif scan_type == "miniprogram":
        primary_selectors = mp_selectors
        secondary_selectors = qr_selectors
    else:
        primary_selectors = qr_selectors + mp_selectors

    # 第一轮—第三轮：精确 QR 码匹配 → found_qrcode=True
    # 第一轮：精确匹配
    for sel in primary_selectors:
        try:
            elements = page.query_selector_all(sel)
            for el in elements:
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                if box and box["width"] >= 60 and box["height"] >= 60:
                    img_b64 = base64.b64encode(el.screenshot(type="png")).decode()
                    return _make_qr_result(img_b64)
        except Exception:
            continue

    # 第二轮：次级选择器
    if secondary_selectors:
        for sel in secondary_selectors:
            try:
                elements = page.query_selector_all(sel)
                for el in elements:
                    if not el.is_visible():
                        continue
                    box = el.bounding_box()
                    if box and box["width"] >= 60 and box["height"] >= 60:
                        img_b64 = base64.b64encode(el.screenshot(type="png")).decode()
                        return _make_qr_result(img_b64)
            except Exception:
                continue

    # 第三轮：QR 容器内部的元素
    try:
        for sel in container_selectors:
            containers = page.query_selector_all(sel)
            for container in containers:
                if not container.is_visible():
                    continue
                inner = container.query_selector("canvas, img")
                if inner:
                    box = inner.bounding_box()
                    if box and box["width"] >= 60 and box["height"] >= 60:
                        img_b64 = base64.b64encode(inner.screenshot(type="png")).decode()
                        return _make_qr_result(img_b64)
                box = container.bounding_box()
                if box and box["width"] >= 80 and box["height"] >= 80:
                    img_b64 = base64.b64encode(container.screenshot(type="png")).decode()
                    return _make_qr_result(img_b64)
    except Exception:
        pass

    # 第四轮—第六轮：降级截图（方形兜底/半屏/全屏）→ found_qrcode=False
    # 第四轮：找面积最大、最显眼的方形图片元素（通用兜底）
    try:
        all_imgs = page.query_selector_all("img[src]")
        best = None
        best_area = 0
        for img in all_imgs:
            try:
                if not img.is_visible():
                    continue
                box = img.bounding_box()
                if not box:
                    continue
                w, h = box["width"], box["height"]
                # 方形筛选：长宽比在 0.7 ~ 1.5 之间
                if w < 60 or h < 60:
                    continue
                ratio = max(w, h) / (min(w, h) or 1)
                if 0.7 <= ratio <= 1.5:
                    area = w * h
                    if area > best_area:
                        best_area = area
                        best = img
            except Exception:
                continue
        if best:
            return {
                "image": base64.b64encode(best.screenshot(type="png")).decode(),
                "found_qrcode": False,
            }
    except Exception:
        pass

    # 第五轮：截取整个视口右半部分（通常二维码在右侧）
    try:
        viewport = page.viewport_size or {"width": 1280, "height": 800}
        clip = {
            "x": viewport["width"] // 2,
            "y": 0,
            "width": viewport["width"] // 2,
            "height": viewport["height"],
        }
        return {
            "image": base64.b64encode(page.screenshot(type="png", clip=clip)).decode(),
            "found_qrcode": False,
        }
    except Exception:
        pass

    # 第六轮：截取全屏
    return {
        "image": base64.b64encode(page.screenshot(type="png", full_page=False)).decode(),
        "found_qrcode": False,
    }


# ─── Cookie 验证 ───────────────────────────────────────

def _check_auth_cookies(platform: str, cookies: list) -> bool:
    """按平台检查真正的认证 Cookie（委派到统一验证器）
    
    使用 phase='keyword' 避免网络请求，保持原有无网络开销特性。
    
    Args:
        platform: 平台名
        cookies: Playwright cookies() 返回的列表
    
    Returns:
        True 表示存在有效认证 Cookie
    """
    from flashsloth.core.cookie_validator import verify_cookie
    return verify_cookie(platform, cookies, input_type="list", phase="keyword")["valid"]


# ─── 平台特定扫码操作 ──────────────────────────────────

def _platform_scan_actions(page, platform: str):
    """执行平台特定的扫码前操作（如点击登录按钮显示二维码面板）
    
    不同的平台可能需要不同的前置操作才能显示二维码：
    - bilibili: 需要先点击登录入口按钮
    - juejin: 可能需要点击"扫码登录"标签
    
    Args:
        page: Playwright page 对象
        platform: 平台名
    """
    if platform == "bilibili":
        try:
            # B站需要先点登录按钮弹出登录面板
            login_btn = page.query_selector(".header-login-entry")
            if login_btn and login_btn.is_visible():
                login_btn.click()
                page.wait_for_timeout(500)
                # 再点击"扫码登录" Tab，因为默认弹出的是密码登录面板
                scan_tab = page.query_selector(
                    "[data-login-type='qrcode'], .qr-login, "
                    "[class*='qrcode-tab'], [class*='scan-login'], "
                    "text=扫码登录, .bili-mini-login, "
                    ".login-tab:has-text('扫码'), "
                    ".login-type:has-text('扫码')"
                )
                if scan_tab:
                    scan_tab.click()
                    page.wait_for_timeout(2000)
        except Exception:
            pass
    
    elif platform == "juejin":
        try:
            # 掘金可能需要切换到扫码登录 Tab
            scan_tab = page.query_selector("[class*='qrcode'], [class*='scan'], .scan-login-tab, [data-login-type='qrcode']")
            if scan_tab and scan_tab.is_visible():
                scan_tab.click()
                page.wait_for_timeout(1500)
        except Exception:
            pass


# ─── 平台扫码类型标注（多方式选择版）─────────────────────
# 每个平台可定义多种扫码方式，前端提供选择。
# 为向后兼容，保留顶层 scan_app/hint/type（来自第一个 method）。

PLATFORM_SCAN_INFO = {
    "bilibili": {
        "login_url": "https://www.bilibili.com/",
        "scan_app": "B站官方App",
        "hint": "请打开B站App，使用扫一扫功能扫描此二维码",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "bilibili_app",
                "name": "B站官方App扫码",
                "scan_app": "B站官方App",
                "hint": "请打开B站App，使用扫一扫功能扫描此二维码",
                "type": "qrcode",
            },
        ],
    },
    "wechat": {
        "login_url": "https://mp.weixin.qq.com/",
        "scan_app": "微信",
        "hint": "请打开微信扫一扫扫描此二维码",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "wechat_scan",
                "name": "微信扫码",
                "scan_app": "微信",
                "hint": "请打开微信扫一扫扫描此二维码",
                "type": "qrcode",
            },
        ],
    },
    "discuz": {
        "login_url": "",
        "scan_app": "微信/手机浏览器",
        "hint": "部分Discuz论坛支持扫码登录，请用微信或手机浏览器扫描",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "discuz_scan",
                "name": "微信/浏览器扫码",
                "scan_app": "微信/手机浏览器",
                "hint": "部分Discuz论坛支持扫码登录，请用微信或手机浏览器扫描",
                "type": "qrcode",
            },
        ],
    },
    "juejin": {
        "login_url": "https://juejin.cn/",
        "scan_app": "掘金App/微信",
        "hint": "请打开掘金App扫一扫，或使用微信扫描",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "juejin_app",
                "name": "掘金App扫码",
                "scan_app": "掘金App",
                "hint": "请打开掘金App扫一扫，或使用微信扫描",
                "type": "qrcode",
            },
        ],
    },
    "zhihu": {
        "login_url": "https://www.zhihu.com/signin",
        "scan_app": "知乎App",
        "hint": "请打开知乎App，使用扫一扫功能扫描此二维码",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "zhihu_app",
                "name": "知乎App扫码",
                "scan_app": "知乎App",
                "hint": "请打开知乎App，使用扫一扫功能扫描此二维码",
                "type": "qrcode",
            },
        ],
    },
    "oshwhub": {
        "login_url": "https://passport.jlc.com/login",
        "scan_app": "微信/手机浏览器",
        "hint": "请用微信或手机浏览器扫描此二维码登录立创开源硬件平台",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "oshwhub_scan",
                "name": "微信/浏览器扫码",
                "scan_app": "微信/手机浏览器",
                "hint": "请用微信或手机浏览器扫描此二维码登录立创开源硬件平台",
                "type": "qrcode",
            },
        ],
    },
    "xianyu": {
        "login_url": "https://www.goofish.com/",
        "scan_app": "闲鱼App/淘宝App",
        "hint": "请打开闲鱼或淘宝App扫描此二维码",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "xianyu_app",
                "name": "闲鱼App扫码",
                "scan_app": "闲鱼App",
                "hint": "请打开闲鱼App扫描此二维码",
                "type": "qrcode",
            },
            {
                "id": "taobao_app",
                "name": "淘宝App扫码",
                "scan_app": "淘宝App",
                "hint": "请打开淘宝App扫描此二维码",
                "type": "qrcode",
            },
        ],
    },
    "csdn": {
        "login_url": "https://passport.csdn.net/login",
        "scan_app": "CSDN官方App/微信",
        "hint": "请打开CSDN App扫一扫，或使用微信扫描此二维码",
        "type": "qrcode",
        "scan_methods": [
            {
                "id": "csdn_app",
                "name": "CSDN App扫码",
                "scan_app": "CSDN官方App",
                "hint": "请打开CSDN App使用扫一扫功能",
                "type": "qrcode",
            },
            {
                "id": "wechat",
                "name": "微信扫码",
                "scan_app": "微信",
                "hint": "请打开微信扫一扫扫描此二维码",
                "type": "qrcode",
            },
        ],
    },
}


# ─── Worker 线程 ───────────────────────────────────────

def _scan_login_worker(platform: str, login_url: str, scan_type: str,
                       sess_id: str, result_queue: queue.Queue,
                       timeout_minutes: int = 10):
    """扫码登录后台工作线程 — 复用常驻 BrowserEngine 浏览器实例

    使用 BrowserEngine 的 create_isolated_context() 在共享浏览器上创建
    独立上下文/页面进行扫码登录轮询。不再独立 launch/close 浏览器。

    Args:
        platform: 平台名
        login_url: 登录 URL
        scan_type: "qrcode" | "miniprogram" | "auto"
        sess_id: 会话 ID
        result_queue: 结果队列
        timeout_minutes: 超时分钟数，超时后自动释放资源（默认 10 分钟）
    """
    _ctx = None
    _page = None
    _worker_started = time.time()

    try:
        import base64
        from flashsloth.core.browser_engine import BrowserEngine

        _engine = BrowserEngine.get_instance()
        if not _engine.is_ready():
            ok = _engine.start()
            if not ok:
                raise RuntimeError(f"BrowserEngine failed to start (status={_engine.get_status()['status']})")
        _engine.keep_alive()

        _ctx = _engine.create_isolated_context()
        if not _ctx:
            raise RuntimeError("BrowserEngine failed to create isolated context")
        _page = _ctx.new_page()

        # 导航到登录页
        _page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        _page.wait_for_timeout(3000)

        # 平台特定的扫码前操作
        _platform_scan_actions(_page, platform)

        # 确定实际扫描类型
        actual_scan_type = scan_type
        if actual_scan_type == "auto":
            actual_scan_type = _detect_scan_type(_page)

        # 截图并检查是否找到二维码
        img_result = _screenshot_scan_code(_page, actual_scan_type)
        page_title = _page.title()

        # 如果 scan_type 明确传了 "qrcode" 但没找到二维码，直接返回错误
        if not img_result.get("found_qrcode", False):
            if scan_type == "qrcode":
                result_queue.put({
                    "success": False,
                    "error": "未在页面检测到二维码，该平台可能不支持扫码登录",
                    "no_qrcode": True,
                })
                return
            # auto 模式没找到二维码：仍然发图片但标记 no_qrcode，
            # 让调用方决定是否继续（有些平台的二维码需用户交互后才出现）
            result_queue.put({
                "success": True,
                "image": img_result["image"],
                "found_qrcode": False,
                "page_title": page_title,
                "scan_type": actual_scan_type,
                "warning": "未检测到二维码元素，截图仅供参考",
            })
        else:
            result_queue.put({
                "success": True,
                "image": img_result["image"],
                "found_qrcode": True,
                "page_title": page_title,
                "scan_type": actual_scan_type,
            })

        # 将 Playwright 对象存入 session 供 poll 使用
        sess = _scan_login_sessions.get(sess_id)
        if sess:
            sess["_context"] = _ctx
            sess["_page"] = _page
            sess["_ready"] = True
            sess["_scan_type"] = actual_scan_type

        # 轮询循环 — 每 3 秒检查一次是否退出或需要检查登录态
        # timeout_minutes 分钟超时自动清理：防止前端未调 close 导致资源泄漏（铁律 R7）
        _timeout_seconds = timeout_minutes * 60
        while True:
            if time.time() - _worker_started > _timeout_seconds:
                break
            sess = _scan_login_sessions.get(sess_id)
            if not sess or sess.get("_stop", False):
                break
            poll_flag = sess.get("_poll_requested", False)
            if poll_flag:
                sess["_poll_requested"] = False
                try:
                    cookies = _ctx.cookies()
                    current_url = _page.url.lower()
                    on_login_page = any(
                        kw in current_url
                        for kw in ["login", "signin", "passport", "oauth", "logon"]
                    )
                    has_auth_cookies = _check_auth_cookies(platform, cookies)
                    all_cookies_str = "; ".join(
                        [f"{c['name']}={c['value']}" for c in cookies]
                    )
                    body_text = ""
                    try:
                        body_text = _page.inner_text("body")[:500]
                    except Exception:
                        pass
                    sc_result = _screenshot_scan_code(_page, sess.get("_scan_type", "auto"))
                    sc_b64 = sc_result.get("image", "")

                    # OSHWHub(passport.jlc.com) QR scan may stay on login page
                    # but still have auth cookies set — treat as logged_in
                    if platform == "oshwhub" and has_auth_cookies:
                        sess["_poll_result"] = {
                            "status": "logged_in",
                            "cookies": all_cookies_str,
                            "image": sc_b64,
                        }
                    elif has_auth_cookies and not on_login_page:
                        sess["_poll_result"] = {
                            "status": "logged_in",
                            "cookies": all_cookies_str,
                            "image": sc_b64,
                        }
                    elif on_login_page:
                        sess["_poll_result"] = {
                            "status": "waiting",
                            "image": sc_b64,
                            "url": _page.url[:100],
                            "page_preview": body_text[:300],
                        }
                    else:
                        sess["_poll_result"] = {
                            "status": "unknown",
                            "image": sc_b64,
                            "cookies_count": len(cookies),
                            "page_preview": body_text[:300],
                        }
                except Exception as e:
                    sess["_poll_result"] = {"status": "error", "error": str(e)[:80]}
            time.sleep(3)

    except Exception as e:
        result_queue.put({"success": False, "error": str(e)[:100]})
    finally:
        for obj in [_page, _ctx]:
            try:
                if obj and hasattr(obj, 'close'):
                    obj.close()
            except Exception:
                pass


# ═══════════════════════════════════════════════════════
# ScanLoginEngine — 统一扫码登录引擎
# ═══════════════════════════════════════════════════════

class ScanLoginEngine:
    """扫码登录引擎 — 统一处理所有扫码类登录方式
    
    提供 start / poll / close 三阶段生命周期：
    - start: 启动后台浏览器 -> 截图扫码元素 -> 返回 session_id + 图片
    - poll: 轮询登录状态 -> 检测 Cookie -> 返回登录结果
    - close: 关闭浏览器 -> 清理资源
    """

    @staticmethod
    def start_scan_login(platform: str, login_url: str,
                         scan_type: str = "auto",
                         account_id: int = 0,
                         user_id: int = 0,
                         timeout_minutes: int = 10) -> dict:
        """统一扫码登录入口
        
        Args:
            platform: 平台名（如 "bilibili", "wechat", "juejin"）
            login_url: 登录页面 URL
            scan_type: "qrcode" | "miniprogram" | "auto" (自动检测)
            account_id: 关联的账号 ID（可选）
            user_id: 用户 ID
            timeout_minutes: 超时分钟数（默认 10 分钟）
        
        Returns:
            dict: {
                "success": True/False,
                "session_id": str,  # 成功时返回
                "image": str,       # base64 图片
                "scan_type": str,   # 实际检测到的扫描类型
                "page_title": str,
                "error": str,       # 失败时返回
            }
        """
        # 从 playwright_config 读取超时配置（兜底 10 分钟）
        # 显式传入的 timeout_minutes 优先于配置
        _pw_timeout = timeout_minutes
        try:
            from flashsloth.core.database import get_db
            conn = get_db()
            row = conn.execute(
                "SELECT config_json FROM playwright_config WHERE id=1"
            ).fetchone()
            conn.close()
            if row and row["config_json"]:
                cfg = json.loads(row["config_json"])
                _cfg_timeout = cfg.get("qr_login_timeout_minutes", None)
                if _cfg_timeout is not None:
                    _pw_timeout = _cfg_timeout
        except Exception:
            pass

        sess_id = f"scan_{user_id}_{platform}_{int(time.time())}"
        lock = _get_scan_lock(sess_id)
        
        try:
            with lock:
                # 创建 session 记录
                result_queue: queue.Queue = queue.Queue()
                _scan_login_sessions[sess_id] = {
                    "platform": platform,
                    "created_at": time.time(),
                    "status": "starting",
                    "user_id": user_id,
                    "account_id": account_id,
                    "scan_type": scan_type,
                    "_ready": False,
                    "_stop": False,
                    "_poll_requested": False,
                    "_poll_result": None,
                    "_thread": None,
                }

                # 启动后台工作线程
                worker = threading.Thread(
                    target=_scan_login_worker,
                    args=(platform, login_url, scan_type, sess_id, result_queue, _pw_timeout),
                    daemon=True,
                )
                worker.start()
                _scan_login_sessions[sess_id]["_thread"] = worker

                # 等待截图（最多 35 秒）
                try:
                    result = result_queue.get(timeout=35)
                except queue.Empty:
                    result = {"success": False, "error": "浏览器启动超时"}

                if result.get("success"):
                    # 校验二维码截图质量
                    if not result.get("found_qrcode", False):
                        _scan_login_sessions.pop(sess_id, None)
                        _scan_login_locks.pop(sess_id, None)
                        return {
                            "success": False,
                            "error": result.get("validation_error", "获取二维码失败，请重试"),
                        }

                    _scan_login_sessions[sess_id]["status"] = "waiting"
                    scan_info = PLATFORM_SCAN_INFO.get(platform, {})
                    return {
                        "success": True,
                        "session_id": sess_id,
                        "image": result["image"],
                        "scan_type": result.get("scan_type", scan_type),
                        "page_title": result.get("page_title", ""),
                        "scan_info": scan_info,
                        "scan_app": scan_info.get("scan_app", ""),
                        "scan_hint": scan_info.get("hint", ""),
                        "message": "请扫码完成登录",
                    }
                else:
                    _scan_login_sessions.pop(sess_id, None)
                    _scan_login_locks.pop(sess_id, None)
                    return {
                        "success": False,
                        "error": result.get("error", "启动失败"),
                    }

        except Exception as e:
            _scan_login_sessions.pop(sess_id, None)
            _scan_login_locks.pop(sess_id, None)
            return {"success": False, "error": f"扫码登录启动异常: {str(e)[:100]}"}

    @staticmethod
    def poll_scan_login(session_id: str, user_id: int = 0) -> dict:
        """轮询扫码登录状态
        
        Args:
            session_id: start_scan_login 返回的 session_id
            user_id: 用户 ID（用于权限验证）
        
        Returns:
            dict: {
                "success": True,
                "status": "waiting" | "logged_in" | "starting" | "expired" | "error",
                "image": str,        # base64 截图
                "cookies": str,      # 登录成功时返回 Cookie 字符串
                "error": str,        # 错误时返回
                ...
            }
        """
        sess = _scan_login_sessions.get(session_id)
        if not sess:
            return {"success": False, "error": "会话已过期或不存在", "status": "expired"}

        if user_id and sess.get("user_id") and sess["user_id"] != user_id:
            return {"success": False, "error": "无权限", "status": "forbidden"}

        if not sess.get("_ready", False):
            return {"success": True, "status": "starting", "message": "⏳ 浏览器正在启动..."}

        # 请求后台线程检查登录态
        sess["_poll_requested"] = True

        # 等待结果（最多 15 秒）
        deadline = time.time() + 15
        while time.time() < deadline:
            result = sess.get("_poll_result")
            if result is not None:
                sess["_poll_result"] = None
                status = result.get("status", "error")
                if status == "logged_in":
                    return {
                        "success": True,
                        "status": "logged_in",
                        "cookies": result.get("cookies", ""),
                        "image": result.get("image", ""),
                        "message": "✅ 登录成功！Cookie 已获取",
                    }
                elif status == "waiting":
                    return {
                        "success": True,
                        "status": "waiting",
                        "image": result.get("image", ""),
                        "url": result.get("url", ""),
                        "page_preview": result.get("page_preview", ""),
                        "message": "🔍 请扫码完成登录",
                    }
                else:
                    return {
                        "success": True,
                        "status": "unknown",
                        "image": result.get("image", ""),
                        "cookies_count": result.get("cookies_count", 0),
                        "page_preview": result.get("page_preview", ""),
                        "message": "⏳ 等待登录完成...",
                    }
            time.sleep(0.5)

        return {"success": True, "status": "checking", "message": "⏳ 正在检查登录状态..."}

    @staticmethod
    def close_scan_login(session_id: str) -> bool:
        """关闭扫码登录浏览器会话
        
        Args:
            session_id: start_scan_login 返回的 session_id
        
        Returns:
            bool: 是否成功关闭
        """
        sess = _scan_login_sessions.pop(session_id, None)
        if sess:
            sess["_stop"] = True
            thread = sess.get("_thread")
            if thread:
                thread.join(timeout=5)
            _scan_login_locks.pop(session_id, None)
            return True
        return False


# ═══════════════════════════════════════════════════════
# 统一凭证管理（verify_credential / get_credential / save_credential）
# ═══════════════════════════════════════════════════════


def verify_credential(platform: str, account_id: int, user_id: int) -> dict:
    """验证指定账号的凭证是否仍有效

    从 DB 读取 platform_accounts 记录，解密 config_json 获取 cookie，
    调用 cookie_validator.verify_cookie() 做验证。

    Args:
        platform: 平台名
        account_id: 账号 ID
        user_id: 用户 ID

    Returns:
        dict: {"valid": bool, "message": str, "detail": dict}
    """
    from flashsloth.core.database import get_db
    from flashsloth.core.cookie_validator import verify_cookie

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, platform, account_name, config_json, user_id "
            "FROM platform_accounts WHERE id=? AND user_id=?",
            (account_id, user_id),
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if not row:
        return {"valid": False, "message": "账号不存在", "detail": {}}

    cfg = json.loads(row["config_json"]) if row["config_json"] else {}
    decrypt_config(cfg)

    cookie_str = cfg.get("cookie", "") or cfg.get("cookies", "") or ""
    if not cookie_str:
        return {"valid": False, "message": "未配置 Cookie", "detail": {}}

    result = verify_cookie(
        platform=platform,
        cookie_input=cookie_str,
        input_type="string",
        site_url=cfg.get("site_url", ""),
        username_hint=cfg.get("username", ""),
    )

    return {
        "valid": result.get("valid", False),
        "message": result.get("message", ""),
        "detail": result.get("detail", {}),
    }


def get_credential(account_id: int, user_id: int) -> dict:
    """获取指定账号的凭证（Cookie + 配置）

    从 DB 读取记录，解密 config_json。

    Args:
        account_id: 账号 ID
        user_id: 用户 ID

    Returns:
        dict: {"cookie": str, "config": dict}
    """
    from flashsloth.core.database import get_db

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, platform, account_name, config_json, user_id "
            "FROM platform_accounts WHERE id=? AND user_id=?",
            (account_id, user_id),
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if not row:
        return {"cookie": "", "config": {}}

    cfg = json.loads(row["config_json"]) if row["config_json"] else {}
    decrypt_config(cfg)

    cookie = cfg.get("cookie", "") or cfg.get("cookies", "") or ""
    return {"cookie": cookie, "config": cfg}


def save_credential(account_id: int, user_id: int, config: dict) -> bool:
    """保存凭证到 DB（自动加密 config_json）

    加密 config 后写入 platform_accounts.config_json。

    Args:
        account_id: 账号 ID
        user_id: 用户 ID
        config: 配置字典（含 cookie 等敏感字段）

    Returns:
        bool: 是否保存成功
    """
    from flashsloth.core.database import get_db

    encrypt_config(config)
    try:
        conn = get_db()
        conn.execute(
            "UPDATE platform_accounts SET config_json=? WHERE id=? AND user_id=?",
            (json.dumps(config, ensure_ascii=False), account_id, user_id),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def get_session_info(session_id: str) -> Optional[dict]:
    """获取 session 基本信息（不含内部 Playwright 对象）
    
    Args:
        session_id: session 标识
    
    Returns:
        dict 或 None（不存在时）
    """
    from flashsloth.core.credential_provider import _scan_login_sessions
    sess = _scan_login_sessions.get(session_id)
    if not sess:
        return None
    return {
        "platform": sess.get("platform"),
        "status": sess.get("status"),
        "scan_type": sess.get("scan_type"),
        "created_at": sess.get("created_at"),
        "account_id": sess.get("account_id"),
        "user_id": sess.get("user_id"),
        "ready": sess.get("_ready", False),
    }
