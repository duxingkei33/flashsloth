"""FlashSloth Captcha Routes — 验证码/Discuz登录/QR登录"""
import json, time, os, re, threading, random, base64, hashlib, logging
import requests

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.captcha_handler import get_handler, CaptchaProvider
from flashsloth.routes._app import app
from flashsloth.routes.accounts.helpers import _get_engine_for_platform

logger = logging.getLogger(__name__)


# ─── 辅助函数 ─────────────────────────────────────
def generate_token(uid: int, action: str = "auth") -> str:
    """生成一次性操作 token"""
    raw = f"{uid}:{action}:{time.time()}:{random.randint(1000, 9999)}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


# ─── Discuz! 验证码 ──────────────────────────────
@app.route("/api/discuz/captcha", methods=["POST"])
@login_required
def discuz_get_captcha():
    """获取 Discuz! 验证码图片和 session 信息"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (request.json.get("account_id", 0), current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    # 数据驱动（铁律#19）：检查平台是否 discuz 引擎
    engine = _get_engine_for_platform(acct["platform"])
    if engine != "discuz":
        logger.warning(f"[ENGINE MISMATCH] /api/discuz/captcha 被非 discuz 平台调用: platform={acct['platform']}, engine={engine}")
        return jsonify({"success": False, "error": f"平台 {acct['platform']} 不是 Discuz 引擎（{engine}），请使用通用验证码接口"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    site_url = cfg.get("site_url", "").rstrip("/")
    if not site_url:
        return jsonify({"success": False, "error": "未配置站点URL"})

    username = cfg.get("username", "")
    password = cfg.get("password", "")
    if not username or not password:
        return jsonify({"success": False, "error": "未配置用户名或密码"})

    import requests as req
    sess = req.Session()
    # 访问首页获取 Cookie 及 formhash
    try:
        r = sess.get(site_url + "/", timeout=15)
        r.encoding = "gbk"
    except Exception as e:
        return jsonify({"success": False, "error": f"无法连接站点: {e}"})

    html = r.text
    formhash = ""
    import re
    m = re.search(r'name="formhash"\s+value="(\w+)"', html)
    if m:
        formhash = m.group(1)

    # 获取验证码
    import io, base64
    try:
        captcha_resp = sess.get(
            site_url + "/api/mobile/?module=seccode",
            params={"inajax": "1", "idhash": "S00"},
            timeout=10,
        )
        ct = captcha_resp.headers.get("Content-Type", "")
        if "image" in ct:
            img_b64 = base64.b64encode(captcha_resp.content).decode()
        else:
            # 重新尝试常规验证码 URL
            r2 = sess.get(site_url + "/misc.php?mod=seccode&update=1&idhash=S00", timeout=10)
            try:
                data = r2.json()
                img_b64 = data.get("image", "")
            except:
                img_b64 = ""
    except Exception as e:
        return jsonify({"success": False, "error": f"获取验证码失败: {e}"})

    return jsonify({
        "success": True,
        "image": img_b64 or "",
        "formhash": formhash,
        "cookies": "; ".join(f"{k}={v}" for k, v in sess.cookies.get_dict().items()),
        "sid": sess.cookies.get("sid", ""),
    })


@app.route("/api/discuz/login", methods=["POST"])
@login_required
def discuz_login_with_captcha():
    """提交验证码并完成 Discuz! 登录"""
    aid = request.json.get("account_id", 0)
    captcha_code = request.json.get("captcha", "").strip()
    formhash = request.json.get("formhash", "")
    cookie_str = request.json.get("cookies", "")

    if not captcha_code:
        return jsonify({"success": False, "error": "请输入验证码"})

    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    # 数据驱动（铁律#19）：检查平台是否 discuz 引擎
    engine = _get_engine_for_platform(acct["platform"])
    if engine != "discuz":
        logger.warning(f"[ENGINE MISMATCH] /api/discuz/login 被非 discuz 平台调用: platform={acct['platform']}, engine={engine}")
        return jsonify({"success": False, "error": f"平台 {acct['platform']} 不是 Discuz 引擎（{engine}），请使用通用验证码接口"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    username = cfg.get("username", "")
    password = cfg.get("password", "")
    site_url = cfg.get("site_url", "").rstrip("/")

    import requests as req
    from http.cookiejar import Cookie
    sess = req.Session()
    # 重建 Cookie
    if cookie_str:
        for item in cookie_str.split("; "):
            if "=" in item:
                k, v = item.split("=", 1)
                sess.cookies.set(k, v)

    login_data = {
        "username": username,
        "password": password,
        "seccodeverify": captcha_code,
        "formhash": formhash,
        "cookietime": "2592000",
        "loginsubmit": "true",
        "mobile": "yes",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }

    try:
        r = sess.post(
            site_url + "/api/mobile/?module=login",
            data=login_data,
            headers=headers,
            timeout=15,
        )
        r.encoding = "utf-8"
        result = r.json() if r.text.strip().startswith("{") else {"success": False, "error": r.text[:200]}

        if result.get("success") or result.get("Message", {}).get("messageval") == "login_succeed":
            # 登录成功，保存 Cookie
            all_cookies = "; ".join(f"{k}={v}" for k, v in sess.cookies.get_dict().items())
            cfg["cookie"] = all_cookies
            conn = get_db()
            conn.execute(
                "UPDATE platform_accounts SET config_json=?, is_active=1 WHERE id=?",
                (json.dumps(cfg), aid)
            )
            conn.commit()
            conn.close()
            return jsonify({"success": True, "message": "登录成功", "cookies": all_cookies})
        else:
            error_msg = result.get("Message", {}).get("messagestr", "登录失败")
            # 检查验证码错误
            if "seccode" in str(result).lower() or "验证码" in str(result):
                return jsonify({"success": False, "error": "验证码错误或已过期", "needs_captcha": True})
            return jsonify({"success": False, "error": str(error_msg)[:200]})
    except Exception as e:
        return jsonify({"success": False, "error": f"登录请求异常: {e}"})


# ─── 验证码状态/启动/提交 ─────────────────────────
@app.route("/api/captcha/status/<int:aid>", methods=["GET"])
@login_required
def captcha_check_login(aid):
    """检查账号是否需要验证码登录（占位，始终返回 False 表示可直接登录）"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    has_cookie = bool(cfg.get("cookie") or cfg.get("cookies", ""))
    platform = acct["platform"]
    # 静态站点无需验证码
    static_platforms = {"github_pages_blog", "github_pages", "static_site"}
    is_static = platform in static_platforms
    return jsonify({
        "success": True,
        "needs_captcha": False,
        "has_cookie": has_cookie,
        "is_static_site": is_static,
        "status": dict(acct).get("status", ""),
    })


@app.route("/api/captcha/start/<int:aid>", methods=["POST"])
@login_required
def captcha_start_login(aid):
    """启动验证码登录流程 — 获取验证码图片"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    # 静态站点无需验证码登录
    static_platforms = {"github_pages_blog", "github_pages", "static_site"}
    if acct["platform"] in static_platforms:
        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        site_url = cfg.get("site_url", "")
        return jsonify({
            "success": True,
            "needs_captcha": False,
            "is_static_site": True,
            "message": "静态站点无需验证码登录，直接访问站点即可",
            "site_url": site_url,
        })

    return discuz_get_captcha()


@app.route("/api/captcha/submit", methods=["POST"])
@login_required
def captcha_submit():
    """提交验证码完成登录（兼容旧版 /api/discuz/login）"""
    return discuz_login_with_captcha()


@app.route("/api/captcha/provider/<int:aid>", methods=["GET", "POST"])
@login_required
def captcha_provider_config(aid):
    """验证码提供商配置（如 ttshitu / 2captcha）"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    if not acct:
        conn.close()
        return jsonify({"success": False, "error": "账号不存在"})

    if request.method == "POST":
        provider = request.json.get("provider", "manual")
        config = request.json.get("config", {})
        conn.execute(
            "UPDATE platform_accounts SET captcha_provider=?, captcha_config=? WHERE id=?",
            (provider, json.dumps(config), aid)
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "验证码配置已更新"})

    conn.close()
    return jsonify({
        "success": True,
        "provider": acct["captcha_provider"] or "manual",
        "config": json.loads(acct["captcha_config"]) if acct["captcha_config"] else {},
    })


@app.route("/api/captcha/list")
@login_required
def captcha_list_available():
    """列出可用的验证码提供商"""
    providers = get_handler().list_available() if hasattr(get_handler(), 'list_available') else ["manual"]
    return jsonify({"success": True, "providers": providers or ["manual"]})


# ─── 通用验证码/二维码 API ─────────────────────────
@app.route("/api/captcha/solve/auto/<int:aid>", methods=["POST"])
@login_required
def captcha_auto_solve(aid):
    """用配置的自动接码平台识别当前验证码"""
    image_b64 = request.json.get("image", "")
    if not image_b64:
        return jsonify({"success": False, "error": "缺少验证码图片"})
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})
    provider = acct["captcha_provider"] or "manual"
    captcha_config = json.loads(acct["captcha_config"]) if acct["captcha_config"] else {}
    handler = get_handler()
    try:
        if provider == "ttshitu":
            result = handler._solve_ttshitu(image_b64, captcha_config)
        elif provider == "2captcha":
            api_key = captcha_config.get("two_captcha_key", "")
            result = handler._solve_2captcha(image_b64, api_key)
        else:
            return jsonify({"success": False, "error": f"不支持自动识别: {provider}"})
        if result:
            return jsonify({"success": True, "code": result})
        return jsonify({"success": False, "error": "自动识别失败，请尝试手动输入"})
    except Exception as e:
        return jsonify({"success": False, "error": f"自动识别异常: {e}"})


@app.route("/api/captcha/qrcode/start/<int:aid>", methods=["POST"])
@login_required
def captcha_qrcode_start(aid):
    """启动二维码登录 — 获取二维码图片URL并返回"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})
    # 占位实现 — 不同平台的二维码逻辑不同
    return jsonify({"success": False, "error": "二维码登录功能正在开发中"})


@app.route("/api/captcha/qrcode/poll/<int:aid>", methods=["POST"])
@login_required
def captcha_qrcode_poll(aid):
    """轮询二维码扫描状态"""
    return jsonify({"success": False, "error": "二维码登录功能正在开发中"})
