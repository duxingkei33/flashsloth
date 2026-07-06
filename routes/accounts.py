"""FlashSloth — 账号管理路由
从 admin.py 提取，使用 Blueprint 重构"""
from flashsloth.routes._app import app


import json

from flask import ( render_template, request, redirect, url_for,
                  flash, jsonify)
from flask_login import login_required, current_user

from flashsloth.core.database import get_db, DB_PATH
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.credential_crypto import decrypt_config, encrypt_config

# ─── 平台账号管理 ──────────────────────────────
@app.route("/accounts")
@login_required
def accounts():
   conn = get_db()
   accounts = conn.execute(
       "SELECT * FROM platform_accounts WHERE user_id=? ORDER BY platform, created_at",
       (current_user.id,)
   ).fetchall()
   conn.close()
   platforms = list_publishers()
   # 按平台分组
   grouped = {}
   for a in accounts:
       grouped.setdefault(a["platform"], []).append(dict(a))
   return render_template("accounts.html",
                        grouped=grouped,
                        platforms=platforms)

@app.route("/api/accounts/config/<int:aid>")
@login_required
def api_accounts_config(aid):
    """返回指定账号的完整配置（含平台信息）"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    decrypt_config(cfg)  # 解密敏感字段
    cfg["_platform"] = acct["platform"]
    cfg["_accountName"] = acct["account_name"]
    # 脱敏敏感字段
    masked = {}
    for k, v in cfg.items():
        if k.startswith("_"):
            masked[k] = v
        elif k.lower() in SENSITIVE_FIELDS and v:
            masked[k] = MASKED_VALUE
        else:
            masked[k] = v
    return jsonify({"success": True, "config": masked})

@app.route("/accounts/add", methods=["POST"])
@login_required
def add_account():
   platform = request.form.get("platform", "")
   name = request.form.get("account_name", "")
   if not platform or not name:
       if not name:
           # 自动生成不重名默认别名
           conn = get_db()
           existing = conn.execute(
               "SELECT account_name FROM platform_accounts WHERE user_id=? AND platform=?",
               (current_user.id, platform)
           ).fetchall()
           conn.close()
           existing_names = {r["account_name"] for r in existing}
           base = platform
           idx = 1
           while f"{base}{idx:02d}" in existing_names:
               idx += 1
           name = f"{base}{idx:02d}"
       if not platform:
           flash("请选择平台", "error")
           return redirect(url_for("accounts"))
   # 收集该平台的所有配置字段
   cfg = {}
   for key in request.form:
       if key.startswith(f"cfg_"):
           cfg[key[4:]] = request.form[key]

   # 检查是否需要更新已有账号
   edit_id = request.form.get("edit_id", "")
   edit_id_int = int(edit_id) if edit_id and edit_id.isdigit() else 0

   conn = get_db()
   if edit_id_int:
       # 更新已有账号
       existing = conn.execute(
           "SELECT id FROM platform_accounts WHERE id=? AND user_id=?",
           (edit_id_int, current_user.id)
       ).fetchone()
       if existing:
           conn.execute(
               "UPDATE platform_accounts SET account_name=?, config_json=?, is_active=1 WHERE id=?",
               (name, json.dumps(encrypt_config(cfg)), edit_id_int),
           )
           conn.commit()
           conn.close()
           flash(f"{platform} 账号已更新", "success")
           return redirect(url_for("accounts"))
   conn.execute(
       "INSERT INTO platform_accounts (user_id, platform, account_name, config_json) VALUES (?, ?, ?, ?)",
       (current_user.id, platform, name, json.dumps(encrypt_config(cfg))),
   )
   conn.commit()
   conn.close()
   flash(f"{platform} 账号已添加", "success")
   return redirect(url_for("accounts"))

SENSITIVE_FIELDS = {"password", "cookie", "app_secret", "api_key", "token", "access_token", "refresh_token"}
MASKED_VALUE = "••••••••"

@app.route("/accounts/edit/<int:aid>", methods=["GET", "POST"])
@login_required
def edit_account(aid):
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   if not acct:
       flash("账号不存在", "error")
       conn.close()
       return redirect(url_for("accounts"))
   orig_cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   decrypt_config(orig_cfg)  # 解密敏感字段
   
   if request.method == "POST":
       name = request.form.get("account_name", "")
       cfg = {}
       for key in request.form:
           if key.startswith("cfg_"):
               field_key = key[4:]
               val = request.form[key]
               # 如果是掩码占位符，保留原值
               if val == MASKED_VALUE and field_key in orig_cfg:
                   val = orig_cfg[field_key]
               cfg[field_key] = val
       conn.execute(
           "UPDATE platform_accounts SET account_name=?, config_json=?, is_active=? WHERE id=?",
           (name, json.dumps(cfg),
            1 if request.form.get("is_active") else 0, aid),
       )
       conn.commit()
       conn.close()
       flash("账号已更新", "success")
       return redirect(url_for("accounts"))
   
   conn.close()
   
   # 脱敏敏感字段
   masked_cfg = {}
   for k, v in orig_cfg.items():
       if k.lower() in SENSITIVE_FIELDS and v:
           masked_cfg[k] = MASKED_VALUE
       else:
           masked_cfg[k] = v
   
   platforms = list_publishers()
   account_data = dict(acct)
   account_data["config_json"] = json.dumps(masked_cfg)  # 替换为脱敏后的 config
   
   return render_template("account_edit.html",
                        account=account_data,
                        platforms=platforms,
                        has_real_config=bool(orig_cfg.get("password") or orig_cfg.get("cookie")),
                        captcha_provider=acct["captcha_provider"],
                        captcha_config=json.loads(acct["captcha_config"] or "{}"))

@app.route("/accounts/delete/<int:aid>")
@login_required
def delete_account(aid):
   conn = get_db()
   conn.execute("DELETE FROM platform_accounts WHERE id=? AND user_id=?", (aid, current_user.id))
   conn.commit()
   conn.close()
   flash("账号已删除", "success")
   return redirect(url_for("accounts"))

@app.route("/api/accounts/<int:aid>/toggle", methods=["POST"])
@login_required
def api_account_toggle(aid):
   """切换账号启用/禁用状态"""
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   if not acct:
       conn.close()
       return jsonify({"success": False, "error": "账号不存在"})
   new_status = 0 if acct["is_active"] else 1
   conn.execute(
       "UPDATE platform_accounts SET is_active=? WHERE id=?",
       (new_status, aid)
   )
   conn.commit()
   conn.close()
   return jsonify({"success": True, "is_active": bool(new_status)})

@app.route("/api/accounts/<int:aid>/status")
@login_required
def api_account_status(aid):
    """检查账号登录状态 — 全面使用 Playwright 验证登录态，查找用户名信息"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})
    acct = dict(acct)
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    decrypt_config(cfg)  # 解密用于 Playwright 检测
    cookie = cfg.get("cookie", "")
    site_url = cfg.get("site_url", "")
    platform = acct["platform"]
    # 静态站点平台列表（无需 cookie/登录检测，只需检查站点可达性）
    static_platforms = {"github_pages_blog", "github_pages", "static_site"}
    is_static = platform in static_platforms

    result = {
        "success": True,
        "platform": platform,
        "account_name": acct["account_name"],
        "is_active": bool(acct["is_active"]),
        "has_cookie": bool(cookie),
        "has_site_url": bool(site_url),
        "site_url": site_url or "",
        "is_static_site": is_static,
    }

    import re

    # ─── 静态站点处理 ─────────────────────────────
    if is_static and site_url:
        try:
            import requests
            r = requests.get(
                site_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                timeout=15,
                allow_redirects=True,
            )
            result["status_code"] = r.status_code
            tm = re.search(r'<title>(.*?)</title>', r.text)
            result["page_title"] = tm.group(1) if tm else "(无标题)"
            if r.status_code == 200:
                result["logged_in"] = None
                result["status"] = "✅ 站点可浏览"
            else:
                result["logged_in"] = None
                result["status"] = f"⚠️ 站点返回 HTTP {r.status_code}"
        except Exception as e:
            result["logged_in"] = None
            result["status"] = f"❌ 站点不可达: {str(e)[:100]}"
        return jsonify(result)

    # ─── 动态站点：使用 Playwright 全面检测 ─────────
    if not site_url:
        result["logged_in"] = None
        result["status"] = "🔗 未配置站点 URL"
        return jsonify(result)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080}, locale="zh-CN",
            )
            # 如果提供 cookie，注入 cookie
            if cookie:
                domain = site_url.replace("https://", "").replace("http://", "").split("/")[0]
                cookies = []
                for pair in cookie.split(";"):
                    pair = pair.strip()
                    if not pair or "=" not in pair:
                        continue
                    n, v = pair.split("=", 1)
                    cookies.append({"name": n.strip(), "value": v.strip(),
                                    "domain": f".{domain}", "path": "/"})
                ctx.add_cookies(cookies)

            page = ctx.new_page()
            try:
                page.goto(site_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)

                # 获取页面标题和纯文本
                result["page_title"] = page.title()
                body_text = page.inner_text("body")[:2000]
                page_url_lower = page.url.lower()

                # 判断是否被重定向到登录页
                login_keywords_in_url = ["login", "signin", "passport", "oauth", "logon"]
                redirected_to_login = any(kw in page_url_lower for kw in login_keywords_in_url)

                # 查找用户名/用户信息模式
                account_name = acct["account_name"]
                # 尝试查找账号名相关的文本（用户名、欢迎语等）
                username_indicators = []
                # 匹配 "你好，xxx"、"欢迎，xxx"、"xxx，欢迎"、"hello xxx" 等模式
                user_patterns = [
                    rf'{re.escape(account_name)}',
                    rf'欢迎[：:  ].*{re.escape(account_name[:max(2, len(account_name)//2)])}',
                    rf'{re.escape(account_name[:max(2, len(account_name)//2)])}.*欢迎',
                    rf'你好[：: 　].*{re.escape(account_name[:max(2, len(account_name)//2)])}',
                    r'user[=_\s-][A-Za-z0-9_\u4e00-\u9fff]+',
                    r'username[=_\s-][A-Za-z0-9_\u4e00-\u9fff]+',
                    r'nick[=_\s-][A-Za-z0-9_\u4e00-\u9fff]+',
                    r'退出\s*登录',
                    r'注销',
                    r'个人中心',
                    r'我的中心',
                    r'我的帖子',
                    r'我的文章',
                ]
                for pat in user_patterns:
                    m = re.search(pat, body_text, re.IGNORECASE)
                    if m:
                        username_indicators.append(m.group(0)[:80])

                # 提取包含用户名的上下文（前500字节）
                user_context = ""
                if username_indicators:
                    for indicator in username_indicators[:3]:
                        idx = body_text.find(indicator)
                        if idx >= 0:
                            start = max(0, idx - 100)
                            end = min(len(body_text), idx + len(indicator) + 100)
                            snippet = body_text[start:end].strip()
                            user_context += f"...{snippet}...\n"

                is_logged_in = (
                    not redirected_to_login
                    and len(username_indicators) > 0
                ) or (
                    not redirected_to_login
                    and bool(cookie)
                    and len(ctx.cookies()) > 3  # 有足够 cookie 且不在登录页
                )

                result["logged_in"] = is_logged_in
                result["username_found"] = bool(username_indicators)
                result["username_indicators"] = username_indicators[:5]
                result["page_preview"] = user_context[:500] if user_context else body_text[:500]
                result["page_url"] = page.url

                if is_logged_in:
                    if username_indicators:
                        result["status"] = f"✅ 已登录 — 检测到用户信息: {' | '.join(username_indicators[:3])}"
                    else:
                        result["status"] = "✅ 已登录（Cookie 有效）"
                else:
                    reason = "重定向到登录页" if redirected_to_login else "未检测到用户信息"
                    if cookie:
                        result["status"] = f"❌ Cookie 已失效（{reason}）"
                    else:
                        result["status"] = f"❌ 未登录（{reason}）"

            except Exception as e:
                result["logged_in"] = False
                result["status"] = f"❌ 检测异常: {str(e)[:100]}"
                result["page_title"] = page.title() if page else ""
            finally:
                page.close()
                browser.close()
    except Exception as e:
        result["logged_in"] = False
        result["status"] = f"❌ Playwright 初始化异常: {str(e)[:100]}"

    return jsonify(result)

@app.route("/api/accounts/test/<int:aid>", methods=["POST"])
@login_required
def test_account(aid):
   """测试指定账号的连接状态"""
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   conn.close()
   if not acct:
       return jsonify({"success": False, "error": "账号不存在"})
   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   decrypt_config(cfg)  # 解密凭证用于连接测试
   try:
       publisher = get_publisher(acct["platform"], cfg)
       if hasattr(publisher, "test_connection"):
           result = publisher.test_connection()
           return jsonify(result)
       return jsonify({"success": False, "error": "该平台不支持连接测试"})
   except Exception as e:
       return jsonify({"success": False, "error": f"测试异常: {e}"})

@app.route("/api/accounts/<int:aid>/signin_settings", methods=["POST"])
@login_required
def api_account_signin_settings(aid):
   """保存账号的签到设置（启用/禁用、签到时间）"""
   data = request.get_json() or {}
   signin_enabled = data.get("signin_enabled")
   signin_time = data.get("signin_time")
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   if not acct:
       conn.close()
       return jsonify({"success": False, "error": "账号不存在"})
   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   if signin_enabled is not None:
       cfg["signin_enabled"] = bool(signin_enabled)
   if signin_time is not None:
       cfg["signin_time"] = str(signin_time)
   conn.execute(
       "UPDATE platform_accounts SET config_json=? WHERE id=?",
       (json.dumps(cfg), aid)
   )
   conn.commit()
   conn.close()
   return jsonify({"success": True})

@app.route("/api/accounts/<int:aid>/keep_alive", methods=["POST"])
@login_required
def api_account_keep_alive(aid):
   """切换保持在线状态"""
   data = request.get_json() or {}
   keep_alive = data.get("keep_alive")
   if keep_alive is None:
       return jsonify({"success": False, "error": "缺少 keep_alive 参数"})
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   if not acct:
       conn.close()
       return jsonify({"success": False, "error": "账号不存在"})
   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   cfg["keep_alive"] = "1" if keep_alive else "0"
   conn.execute(
       "UPDATE platform_accounts SET config_json=? WHERE id=?",
       (json.dumps(cfg), aid)
   )
   conn.commit()
   conn.close()
   return jsonify({"success": True, "keep_alive": bool(keep_alive)})


# ═══════════════════════════════════════════════════
# 统一平台信息 API
# ═══════════════════════════════════════════════════
@app.route("/api/platforms/list")
@login_required
def api_platforms_list():
	"""返回所有平台信息（含登录方法、配置字段）"""
	from flashsloth.core.publisher import list_publishers
	platforms = list_publishers()
	return jsonify({"success": True, "platforms": platforms})


# ═══════════════════════════════════════════════════
# 统一登录 API — 根据平台和方法分发
# ═══════════════════════════════════════════════════
import threading

_login_locks: dict[str, threading.Lock] = {}


def _get_login_lock(platform: str) -> threading.Lock:
	"""获取平台锁"""
	if platform not in _login_locks:
		_login_locks[platform] = threading.Lock()
	return _login_locks[platform]


@app.route("/api/platform/<platform>/login/start", methods=["POST"])
@login_required
def api_platform_login_start(platform):
	"""统一登录入口：启动浏览器登录"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)
	username = data.get("username", "")
	password = data.get("password", "")
	site_url = data.get("site_url", "")

	if platform in ("amobbs", "discuz"):
		from flashsloth.routes.browser_login import _get_amobbs_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_amobbs_login(sess_id)
			result = inst.login(username, password)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif platform == "xianyu":
		from flashsloth.routes.browser_login import _get_xianyu_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_xianyu_login(sess_id)
			result = inst.login(username, password)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif platform == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_oshwhub_login(sess_id)
			result = inst.login(username, password)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持密码登录"})


@app.route("/api/platform/<platform>/login/captcha", methods=["POST"])
@login_required
def api_platform_login_captcha(platform):
	"""统一登录：提交验证码"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)

	if platform in ("amobbs", "discuz"):
		from flashsloth.routes.browser_login import _get_amobbs_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_amobbs_login(sess_id)
			result = inst.click_captcha_and_submit()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif platform == "xianyu":
		from flashsloth.routes.browser_login import _get_xianyu_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_xianyu_login(sess_id)
			result = inst.solve_and_login()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif platform == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_oshwhub_login(sess_id)
			result = inst.submit_captcha_and_login()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持验证码提交"})


@app.route("/api/platform/<platform>/login/screenshot")
@login_required
def api_platform_login_screenshot(platform):
	"""统一登录：获取页面截图"""
	if platform in ("amobbs", "discuz"):
		from flashsloth.routes.browser_login import _get_amobbs_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_amobbs_login(f"user_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	elif platform == "xianyu":
		from flashsloth.routes.browser_login import _get_xianyu_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_xianyu_login(f"user_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	elif platform == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_oshwhub_login(f"user_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	return jsonify({"success": False, "error": f"平台 {platform} 不支持截图"})


@app.route("/api/platform/<platform>/login/close", methods=["POST"])
@login_required
def api_platform_login_close(platform):
	"""统一登录：关闭浏览器会话"""
	if platform in ("amobbs", "discuz"):
		from flashsloth.routes.browser_login import _amobbs_login_instances
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _amobbs_login_instances.pop(sess_id, None)
			if inst:
				inst.close()
			return jsonify({"success": True})

	elif platform == "xianyu":
		from flashsloth.routes.browser_login import _xianyu_login_instances
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _xianyu_login_instances.pop(sess_id, None)
			if inst:
				inst.close()
			return jsonify({"success": True})

	elif platform == "oshwhub":
		from flashsloth.routes.browser_login import _oshwhub_login_instances
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _oshwhub_login_instances.pop(sess_id, None)
			if inst:
				inst.close()
			return jsonify({"success": True})

	return jsonify({"success": False, "error": f"平台 {platform} 不支持浏览器登录"})


def _save_cookie_to_account(aid: int, cookie_str: str):
	"""保存 Cookie 到账号配置"""
	conn = get_db()
	acct = conn.execute(
		"SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
		(aid, current_user.id)
	).fetchone()
	if acct:
		cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
		cfg["cookie"] = cookie_str
		conn.execute(
			"UPDATE platform_accounts SET config_json=? WHERE id=?",
			(json.dumps(cfg), aid)
		)
		conn.commit()
	conn.close()


