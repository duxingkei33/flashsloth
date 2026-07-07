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

    if scan_type == "auto":
        scan_type = _detect_scan_type(page)

    # QR 码选择器
    qr_selectors = [
        "canvas",
        "img[src*='qrcode' i]",
        "img[src*='qr' i]",
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
                    return {
                        "image": base64.b64encode(el.screenshot(type="png")).decode(),
                        "found_qrcode": True,
                    }
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
                        return {
                            "image": base64.b64encode(el.screenshot(type="png")).decode(),
                            "found_qrcode": True,
                        }
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
                        return {
                            "image": base64.b64encode(inner.screenshot(type="png")).decode(),
                            "found_qrcode": True,
                        }
                box = container.bounding_box()
                if box and box["width"] >= 80 and box["height"] >= 80:
                    return {
                        "image": base64.b64encode(container.screenshot(type="png")).decode(),
                        "found_qrcode": True,
                    }
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
    """按平台检查真正的认证 Cookie（UX2 铁律 — 禁止假阳性）
    
    Args:
        platform: 平台名
        cookies: Playwright cookies() 返回的列表
    
    Returns:
        True 表示存在有效认证 Cookie
    """
    cookie_map = {c["name"]: c.get("value", "") for c in cookies}
    
    if platform == "bilibili":
        # B站需要同时存在三个认证 Cookie 才算登录
        return all(k in cookie_map for k in ["bili_jct", "SESSDATA", "DedeUserID"])
    
    if platform in ("discuz", "amobbs"):
        # Discuz/Amobbs 需要 auth cookie 值非空
        auth_val = cookie_map.get("auth", "")
        return bool(auth_val and auth_val.strip())
    
    if platform == "wechat":
        # 微信/公众号平台需要特定 Cookie
        wx_keys = ["token", "fakeid", "slave_user", "slave_sid"]
        return any(k in cookie_map and cookie_map[k].strip() for k in wx_keys)
    
    # 通用兜底：至少 2 个不同的 auth 类 cookie 且值都非空
    # 防止随机网站的跟踪 cookie（如 _ga_session）误报为登录
    auth_kw = ["auth", "token", "session", "login", "passport"]
    matched = []
    for c in cookies:
        for kw in auth_kw:
            if kw in c["name"].lower() and c.get("value", "").strip():
                if c["name"] not in [m["name"] for m in matched]:
                    matched.append(c)
                    break
    return len(matched) >= 2


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
            # B站需要先点登录按钮弹出二维码面板
            login_btn = page.query_selector(".header-login-entry")
            if login_btn and login_btn.is_visible():
                login_btn.click()
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


# ─── Worker 线程 ───────────────────────────────────────

def _scan_login_worker(platform: str, login_url: str, scan_type: str,
                       sess_id: str, result_queue: queue.Queue):
    """扫码登录后台工作线程 — 拥有独立的 Playwright 浏览器实例
    
    从 routes/accounts.py _qr_worker 适配而来，增加了 scan_type 支持、
    小程序码检测和平台特定操作。
    """
    _pw = None
    _browser = None
    _ctx = None
    _page = None
    _worker_started = time.time()

    try:
        from playwright.sync_api import sync_playwright
        import base64

        _pw = sync_playwright().__enter__()
        _browser = _pw.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox', '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
            ],
        )
        _ctx = _browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        _ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
            window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {}, app: {}};
        """)
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
            sess["_pw"] = _pw
            sess["_browser"] = _browser
            sess["_context"] = _ctx
            sess["_page"] = _page
            sess["_ready"] = True
            sess["_scan_type"] = actual_scan_type

        # 轮询循环 — 每 3 秒检查一次是否退出或需要检查登录态
        # 5 分钟超时自动清理：防止前端未调 close 导致资源泄漏（铁律 R7）
        while True:
            if time.time() - _worker_started > 300:
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

                    if has_auth_cookies and not on_login_page:
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
        for obj in [_page, _ctx, _browser]:
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if _pw:
                _pw.__exit__(None, None, None)
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
                         user_id: int = 0) -> dict:
        """统一扫码登录入口
        
        Args:
            platform: 平台名（如 "bilibili", "wechat", "juejin"）
            login_url: 登录页面 URL
            scan_type: "qrcode" | "miniprogram" | "auto" (自动检测)
            account_id: 关联的账号 ID（可选）
            user_id: 用户 ID
        
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
                    args=(platform, login_url, scan_type, sess_id, result_queue),
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
                    _scan_login_sessions[sess_id]["status"] = "waiting"
                    return {
                        "success": True,
                        "session_id": sess_id,
                        "image": result["image"],
                        "scan_type": result.get("scan_type", scan_type),
                        "page_title": result.get("page_title", ""),
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

    @staticmethod
    def get_session_info(session_id: str) -> Optional[dict]:
        """获取 session 基本信息（不含内部 Playwright 对象）
        
        Args:
            session_id: session 标识
        
        Returns:
            dict 或 None（不存在时）
        """
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


# ═══════════════════════════════════════════════════════
# 凭证存储 — save_credential / get_credential / verify_credential
# ═══════════════════════════════════════════════════════

def save_credential(platform: str, account_id: int,
                    cookies_dict: dict,
                    credential_type: str = "qrcode",
                    user_id: int = 0) -> bool:
    """将 Cookie 凭证加密后存入 platform_accounts.config_json
    
    Args:
        platform: 平台名
        account_id: 账号 ID（platform_accounts.id）
        cookies_dict: Cookie 字典（键值对）或 Cookie 字符串
        credential_type: "qrcode" | "miniprogram" | "password"
        user_id: 用户 ID
    
    Returns:
        bool: 是否成功保存
    """
    try:
        from flashsloth.core.database import get_db

        conn = get_db()
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
            (account_id, user_id),
        ).fetchone()
        if not acct:
            conn.close()
            return False

        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}

        # 统一 Cookie 格式
        if isinstance(cookies_dict, dict):
            cookie_str = "; ".join(
                [f"{k}={v}" for k, v in cookies_dict.items()]
            )
        elif isinstance(cookies_dict, str):
            cookie_str = cookies_dict
        else:
            cookie_str = str(cookies_dict) if cookies_dict else ""

        # 计算过期时间（默认 30 天后）
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()

        # 加密后存入标准字段
        cfg["cookie"] = cookie_str
        cfg["credential_type"] = credential_type
        cfg["captured_at"] = now.isoformat()
        cfg["expires_at"] = expires_at
        cfg["cookies_encrypted"] = True

        encrypt_config(cfg)
        conn.execute(
            "UPDATE platform_accounts SET config_json=? WHERE id=?",
            (json.dumps(cfg), account_id),
        )
        conn.commit()
        conn.close()
        return True

    except Exception:
        return False


def get_credential(platform: str, account_id: int,
                   user_id: int = 0) -> Optional[dict]:
    """获取已保存的凭证
    
    Args:
        platform: 平台名
        account_id: 账号 ID
        user_id: 用户 ID
    
    Returns:
        dict: {
            "cookie": str,           # 解密后的 Cookie 字符串
            "credential_type": str,  # 凭证类型
            "captured_at": str,      # 捕获时间
            "expires_at": str,       # 过期时间
            "platform": str,
            "account_name": str,
        } 或 None（不存在/失败时）
    """
    try:
        from flashsloth.core.database import get_db

        conn = get_db()
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
            (account_id, user_id),
        ).fetchone()
        conn.close()

        if not acct:
            return None

        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        decrypt_config(cfg)

        cookie = cfg.get("cookie", "")
        if not cookie:
            return None

        return {
            "cookie": cookie,
            "credential_type": cfg.get("credential_type", "unknown"),
            "captured_at": cfg.get("captured_at", ""),
            "expires_at": cfg.get("expires_at", ""),
            "platform": acct["platform"],
            "account_name": acct["account_name"],
        }

    except Exception:
        return None


def verify_credential(platform: str, account_id: int,
                      user_id: int = 0) -> dict:
    """验证凭证是否仍有效
    
    使用 status_detector 的轻量 API 检测方式验证 Cookie 是否有效。
    如果平台不支持轻量检测，则返回 uncertain。
    
    Args:
        platform: 平台名
        account_id: 账号 ID
        user_id: 用户 ID
    
    Returns:
        dict: {
            "valid": bool,        # True/False/None (uncertain)
            "message": str,       # 结果说明
            "detail": dict,       # 验证详情
        }
    """
    from flashsloth.core.status_detector import detect_platform, PLATFORM_DETECTORS

    cred = get_credential(platform, account_id, user_id)
    if not cred:
        return {"valid": None, "message": "未找到凭证", "detail": {}}

    cookie = cred.get("cookie", "")
    if not cookie:
        return {"valid": None, "message": "Cookie 为空", "detail": {}}

    # 检查过期时间
    expires_at = cred.get("expires_at", "")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at)
            if datetime.now() > exp:
                return {
                    "valid": False,
                    "message": "凭证已过期",
                    "detail": {"expires_at": expires_at},
                }
        except Exception:
            pass

    # 使用平台特定的状态检测
    if platform in PLATFORM_DETECTORS:
        try:
            result = detect_platform(platform, cookie=cookie)
            logged_in = result.get("logged_in", False)
            return {
                "valid": logged_in,
                "message": "有效" if logged_in else "Cookie 已失效",
                "detail": result,
            }
        except Exception as e:
            return {"valid": None, "message": f"验证异常: {str(e)[:80]}", "detail": {}}

    # 通用验证：尝试用 Cookie 访问平台首页
    try:
        import requests
        headers = {"Cookie": cookie, "User-Agent": "Mozilla/5.0"}
        resp = requests.get(
            f"https://{platform}.com" if "." not in platform else f"https://{platform}",
            headers=headers,
            timeout=10,
        )
        # 简单判断：如果响应中不包含登录页面关键字，可能已登录
        login_kw = ["login", "signin", "登录", "注册"]
        has_login_page = any(kw in resp.text[:2000].lower() for kw in login_kw)
        return {
            "valid": not has_login_page,
            "message": "有效（通用验证）" if not has_login_page else "可能已过期（页面含登录关键字）",
            "detail": {"status_code": resp.status_code, "has_login_page": has_login_page},
        }
    except Exception:
        pass

    return {"valid": None, "message": "无法验证（平台不支持自动检测）", "detail": {}}
