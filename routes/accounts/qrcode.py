"""FlashSloth — 账号管理路由：扫码登录"""
from flashsloth.routes._app import app
from flask import jsonify, request
from flask_login import login_required, current_user

import json
import time
import threading
import queue as _qr_queue

from flashsloth.routes.accounts.crud import _save_cookie_to_account

# ═══════════════════════════════════════════════════
# 统一 QR 码扫码登录 API — 线程安全版
# ═══════════════════════════════════════════════════
# 使用后台线程管理 Playwright 浏览器，避免线程切换问题。
# start → 启动后台线程打开浏览器 → 截图返回 → 线程保持浏览器运行
# poll → 通知后台线程检查登录态 → 返回结果
# close → 通知后台线程关闭浏览器并退出
# ═══════════════════════════════════════════════════

_qr_login_sessions: dict[str, dict] = {}
_qr_login_locks: dict[str, threading.Lock] = {}


def _get_qr_lock(session_id: str) -> threading.Lock:
    if session_id not in _qr_login_locks:
        _qr_login_locks[session_id] = threading.Lock()
    return _qr_login_locks[session_id]


def _screenshot_qr(page):
    """查找页面中的 QR 码元素并截图，降级为截取整个视口"""
    import base64
    # 尝试常见 QR 码元素选择器
    for sel in ["canvas", "img[src*='qrcode' i]", "img[src*='qr' i]"]:
        try:
            elements = page.query_selector_all(sel)
            for el in elements:
                box = el.bounding_box()
                if box and box["width"] >= 80 and box["height"] >= 80:
                    return base64.b64encode(el.screenshot(type="png")).decode()
        except Exception:
            continue
    # 尝试 QR 容器内部的元素
    try:
        containers = page.query_selector_all('[class*="qr" i], [id*="qr" i]')
        for container in containers:
            inner = container.query_selector("canvas, img")
            if inner:
                box = inner.bounding_box()
                if box and box["width"] >= 80 and box["height"] >= 80:
                    return base64.b64encode(inner.screenshot(type="png")).decode()
            box = container.bounding_box()
            if box and box["width"] >= 80 and box["height"] >= 80:
                return base64.b64encode(container.screenshot(type="png")).decode()
    except Exception:
        pass
    # 降级：截取整个视口
    return base64.b64encode(page.screenshot(type="png", full_page=False)).decode()


def _check_auth_cookies(platform: str, cookies: list) -> bool:
    """按平台检查真正的认证 Cookie（委派到统一验证器）

    使用 phase='keyword' 避免网络请求，保持原有无网络开销特性。
    """
    from flashsloth.core.cookie_validator import verify_cookie
    return verify_cookie(platform, cookies, input_type="list", phase="keyword")["valid"]


def _qr_worker(platform: str, login_url: str, sess_id: str, result_queue: _qr_queue.Queue):
    """QR 码登录工作线程 — 使用 BrowserEngine 的隔离上下文"""
    _ctx = None; _page = None
    _worker_started = time.time()

    # 从 BrowserEngine 配置读取超时
    _qr_timeout_seconds = 600  # 兜底 10 分钟
    try:
        from flashsloth.core.browser_engine import BrowserEngine
        _bengine = BrowserEngine.get_instance()
        _bcfg = _bengine.get_config()
        _qr_timeout_seconds = _bcfg.get("qr_login_timeout_minutes", 10) * 60
    except Exception:
        pass
    try:
        import base64

        # 使用 BrowserEngine 创建隔离上下文（共享浏览器进程，隔离 Cookie）
        from flashsloth.core.browser_engine import BrowserEngine
        _bengine = BrowserEngine.get_instance()
        if not _bengine.is_ready():
            _bengine.start()
        _ctx = _bengine.create_isolated_context()
        if not _ctx:
            raise RuntimeError("无法从 BrowserEngine 获取隔离上下文")
        _page = _ctx.new_page()

        # 导航到登录页
        _page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        _page.wait_for_timeout(3000)

        # 对于 Bilibili：需要点击登录按钮弹出二维码面板
        if platform == "bilibili":
            try:
                login_btn = _page.query_selector(".header-login-entry")
                if login_btn and login_btn.is_visible():
                    login_btn.click()
                    _page.wait_for_timeout(2000)
            except Exception:
                pass

        # 截图并放入队列
        img_b64 = _screenshot_qr(_page)
        page_title = _page.title()
        result_queue.put({"success": True, "image": img_b64, "page_title": page_title})

        # 将 Playwright 对象存入 session 供 poll 使用
        sess = _qr_login_sessions.get(sess_id)
        if sess:
            sess["_context"] = _ctx
            sess["_page"] = _page
            sess["_ready"] = True

        # 轮询循环 — 每 3 秒检查一次是否退出或需要检查登录态
        # 5 分钟超时自动清理：防止前端未调 /close 导致资源泄漏
        while True:
            # 超时检查：启动后超过 5 分钟自动退出
            if time.time() - _worker_started > _qr_timeout_seconds:
                break
            sess = _qr_login_sessions.get(sess_id)
            if not sess or sess.get("_stop", False):
                break
            # 检查是否有 poll 信号
            poll_flag = sess.get("_poll_requested", False)
            if poll_flag:
                sess["_poll_requested"] = False
                try:
                    cookies = _ctx.cookies()
                    current_url = _page.url.lower()
                    on_login_page = any(kw in current_url for kw in ["login", "signin", "passport", "oauth", "logon"])
                    has_auth_cookies = _check_auth_cookies(platform, cookies)
                    all_cookies_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    body_text = ""
                    try:
                        body_text = _page.inner_text("body")[:500]
                    except Exception:
                        pass
                    sc_b64 = _screenshot_qr(_page)

                    if has_auth_cookies and not on_login_page:
                        sess["_poll_result"] = {"status": "logged_in", "cookies": all_cookies_str, "image": sc_b64}
                    elif on_login_page:
                        sess["_poll_result"] = {"status": "waiting", "image": sc_b64, "url": _page.url[:100], "page_preview": body_text[:300]}
                    else:
                        sess["_poll_result"] = {"status": "unknown", "image": sc_b64, "cookies_count": len(cookies), "page_preview": body_text[:300]}
                except Exception as e:
                    sess["_poll_result"] = {"status": "error", "error": str(e)[:80]}

            time.sleep(3)

    except Exception as e:
        result_queue.put({"success": False, "error": str(e)[:100]})
    finally:
        # 只清除上下文（浏览器由 BrowserEngine 管理）
        for obj in [_page, _ctx]:
            try:
                if obj: obj.close()
            except Exception: pass


@app.route("/api/login/qrcode/<platform>/start", methods=["POST"])
@login_required
def api_qrcode_login_start(platform):
    """启动 QR 码扫码登录 — 委托统一扫码登录引擎"""
    data = request.get_json() or {}
    aid = data.get("account_id", 0)
    site_url = data.get("site_url", "")
    method = data.get("method", "")  # scan_methods[].id — 可选

    # 确定登录 URL
    login_url = data.get("login_url", site_url or "")
    if not login_url:
        login_page_map = {
            "discuz": "/member.php?mod=logging&action=login",
            "amobbs": "/member.php?mod=logging&action=login",
            "csdn": "https://passport.csdn.net/login",
            "oshwhub": "https://passport.jlc.com/login",
            "xianyu": "https://www.goofish.com/",
            "xianyu_v2": "https://www.goofish.com/",
            "wechat": "https://mp.weixin.qq.com/",
            "zhihu": "https://www.zhihu.com/signin",
            "bilibili": "https://www.bilibili.com/",
            "juejin": "https://juejin.cn/",
            "wordpress": f"{site_url.rstrip('/')}/wp-login.php" if site_url else "",
        }
        login_url = login_page_map.get(platform, site_url or "")
    if not login_url:
        return jsonify({"success": False, "error": "未知登录地址，请提供 site_url"})

    # 若前台传了 method，查找到对应 method 的 scan_info 作为返回值
    extra_scan_info = {}
    if method:
        from flashsloth.core.credential_provider import PLATFORM_SCAN_INFO as _PSI
        _platform_info = _PSI.get(platform, {})
        for _m in _platform_info.get("scan_methods", []):
            if _m.get("id") == method:
                extra_scan_info = {
                    "scan_app": _m.get("scan_app", ""),
                    "scan_hint": _m.get("hint", ""),
                }
                break

    # 委托统一扫码登录引擎
    from flashsloth.core.credential_provider import ScanLoginEngine
    result = ScanLoginEngine.start_scan_login(
        platform=platform,
        login_url=login_url,
        scan_type="qrcode",
        account_id=aid,
        user_id=current_user.id,
    )

    if result.get("success"):
        # 如果前台传了 method，优先使用 method 对应的 scan_app/scan_hint
        _scan_app = extra_scan_info.get("scan_app") or result.get("scan_app", "")
        _scan_hint = extra_scan_info.get("scan_hint") or result.get("scan_hint", "")
        # 将旧的 session_id 映射到新引擎 session，以便旧 poll/close 能工作
        _qr_login_sessions[result["session_id"]] = {
            "platform": platform,
            "created_at": time.time(),
            "status": "waiting",
            "user_id": current_user.id,
            "account_id": aid,
            "_engine_session": True,
        }
        return jsonify({
            "success": True,
            "session_id": result["session_id"],
            "image": result["image"],
            "page_title": result.get("page_title", ""),
            "scan_info": result.get("scan_info", {}),
            "scan_app": _scan_app,
            "scan_hint": _scan_hint,
            "message": "请扫码完成登录，系统将自动捕获 Cookie",
        })
    else:
        return jsonify({"success": False, "error": result.get("error", "启动失败")})


@app.route("/api/login/scan/<platform>/start", methods=["POST"])
@login_required
def api_scan_login_start(platform):
    """统一扫码登录入口 — 支持 QR 码/小程序码/自动检测"""
    data = request.get_json() or {}
    aid = data.get("account_id", 0)
    site_url = data.get("site_url", "")
    scan_type = data.get("scan_type", "auto")
    method = data.get("method", "")  # scan_methods[].id — 可选，用于前端选择

    # 确定登录 URL
    login_url = data.get("login_url", site_url or "")
    if not login_url:
        login_page_map = {
            "discuz": "/member.php?mod=logging&action=login",
            "amobbs": "/member.php?mod=logging&action=login",
            "csdn": "https://passport.csdn.net/login",
            "oshwhub": "https://passport.jlc.com/login",
            "xianyu": "https://www.goofish.com/",
            "xianyu_v2": "https://www.goofish.com/",
            "wechat": "https://mp.weixin.qq.com/",
            "zhihu": "https://www.zhihu.com/signin",
            "bilibili": "https://www.bilibili.com/",
            "juejin": "https://juejin.cn/",
            "wordpress": f"{site_url.rstrip('/')}/wp-login.php" if site_url else "",
        }
        login_url = login_page_map.get(platform, site_url or "")
    if not login_url:
        return jsonify({"success": False, "error": "未知登录地址，请提供 site_url"})

    # 若前台传了 method，查找到对应 method 的 scan_info 作为返回值
    extra_scan_info = {}
    if method:
        from flashsloth.core.credential_provider import PLATFORM_SCAN_INFO as _PSI
        _platform_info = _PSI.get(platform, {})
        for _m in _platform_info.get("scan_methods", []):
            if _m.get("id") == method:
                extra_scan_info = {
                    "scan_app": _m.get("scan_app", ""),
                    "scan_hint": _m.get("hint", ""),
                }
                break

    # 委托统一扫码登录引擎
    from flashsloth.core.credential_provider import ScanLoginEngine
    result = ScanLoginEngine.start_scan_login(
        platform=platform,
        login_url=login_url,
        scan_type=scan_type,
        account_id=aid,
        user_id=current_user.id,
    )

    if result.get("success"):
        # 如果前台传了 method，优先使用 method 对应的 scan_app/scan_hint
        _scan_app = extra_scan_info.get("scan_app") or result.get("scan_app", "")
        _scan_hint = extra_scan_info.get("scan_hint") or result.get("scan_hint", "")
        return jsonify({
            "success": True,
            "session_id": result["session_id"],
            "image": result["image"],
            "scan_type": result.get("scan_type", scan_type),
            "page_title": result.get("page_title", ""),
            "scan_info": result.get("scan_info", {}),
            "scan_app": _scan_app,
            "scan_hint": _scan_hint,
            "message": "请扫码完成登录，系统将自动捕获 Cookie",
        })
    else:
        return jsonify({"success": False, "error": result.get("error", "启动失败")})


@app.route("/api/login/qrcode/<platform>/poll/<session_id>")
@login_required
def api_qrcode_login_poll(platform, session_id):
    """轮询 QR 码/截图登录状态（委托后台线程检查）"""
    sess = _qr_login_sessions.get(session_id)
    if not sess:
        return jsonify({"success": False, "error": "会话已过期或不存在", "status": "expired"})
    if sess["user_id"] != current_user.id:
        return jsonify({"success": False, "error": "无权限", "status": "forbidden"})

    # 委托统一扫码引擎（如果 session 由引擎创建）
    if sess.get("_engine_session"):
        from flashsloth.core.credential_provider import ScanLoginEngine
        engine_result = ScanLoginEngine.poll_scan_login(session_id, user_id=current_user.id)
        status = engine_result.get("status", "error")

        # 登录成功时保存 Cookie 到账号
        if status == "logged_in":
            cookies_str = engine_result.get("cookies", "")
            aid = sess.get("account_id")
            if aid:
                _save_cookie_to_account(aid, cookies_str)
            return jsonify({
                "success": True,
                "status": "logged_in",
                "cookies": cookies_str,
                "image": engine_result.get("image", ""),
                "message": "✅ 登录成功！Cookie 已自动获取",
            })
        elif status == "waiting":
            return jsonify({
                "success": True,
                "status": "waiting",
                "image": engine_result.get("image", ""),
                "url": engine_result.get("url", ""),
                "page_preview": engine_result.get("page_preview", ""),
                "message": "🔍 请查看截图，在浏览器中完成登录",
            })
        elif status == "expired":
            _qr_login_sessions.pop(session_id, None)
            return jsonify({"success": False, "error": "会话已过期", "status": "expired"})
        else:
            return jsonify({
                "success": True,
                "status": engine_result.get("status", "unknown"),
                "image": engine_result.get("image", ""),
                "cookies_count": engine_result.get("cookies_count", 0),
                "page_preview": engine_result.get("page_preview", ""),
                "message": engine_result.get("message", "⏳ 等待登录完成..."),
            })

    # 旧版 session 处理（向后兼容）
    if not sess.get("_ready", False):
        return jsonify({"success": True, "status": "starting", "message": "⏳ 浏览器正在启动..."})

    # 请求后台线程检查登录态
    sess["_poll_requested"] = True
    # 等待结果（最多 15 秒）
    import time as _t
    deadline = _t.time() + 15
    while _t.time() < deadline:
        result = sess.get("_poll_result")
        if result is not None:
            sess["_poll_result"] = None
            status = result.get("status", "error")
            if status == "logged_in":
                cookies_str = result.get("cookies", "")
                aid = sess.get("account_id")
                if aid:
                    _save_cookie_to_account(aid, cookies_str)
                return jsonify({
                    "success": True,
                    "status": "logged_in",
                    "cookies": cookies_str,
                    "image": result.get("image", ""),
                    "message": "✅ 登录成功！Cookie 已自动获取",
                })
            elif status == "waiting":
                return jsonify({
                    "success": True,
                    "status": "waiting",
                    "image": result.get("image", ""),
                    "url": result.get("url", ""),
                    "page_preview": result.get("page_preview", ""),
                    "message": "🔍 请查看截图，在浏览器中完成登录",
                })
            else:
                return jsonify({
                    "success": True,
                    "status": "unknown",
                    "image": result.get("image", ""),
                    "cookies_count": result.get("cookies_count", 0),
                    "page_preview": result.get("page_preview", ""),
                    "message": "⏳ 等待登录完成...",
                })
        _t.sleep(0.5)

    return jsonify({"success": True, "status": "checking", "message": "⏳ 正在检查登录状态..."})


@app.route("/api/login/qrcode/<platform>/close/<session_id>", methods=["POST"])
@login_required
def api_qrcode_login_close(platform, session_id):
    """关闭 QR 码登录浏览器会话（通知后台线程退出）"""
    sess = _qr_login_sessions.pop(session_id, None)
    if sess:
        # 委托统一扫码引擎关闭（如果 session 由引擎创建）
        if sess.get("_engine_session"):
            from flashsloth.core.credential_provider import ScanLoginEngine
            ScanLoginEngine.close_scan_login(session_id)
        else:
            sess["_stop"] = True
            thread = sess.get("_thread")
            if thread:
                thread.join(timeout=5)
            _qr_login_locks.pop(session_id, None)
    return jsonify({"success": True})
