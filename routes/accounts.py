"""FlashSloth — 账号管理路由
从 admin.py 提取，使用 Blueprint 重构"""
from flashsloth.routes._app import app


import json
import os
import time
from datetime import datetime

from flask import ( render_template, request, redirect, url_for,
                  flash, jsonify)
from flask_login import login_required, current_user

from flashsloth.core.database import get_db, DB_PATH
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.credential_crypto import decrypt_config, encrypt_config
from flashsloth.core.status_cache import (
    get_status, set_status, invalidate, get_all_cached, get_cache_stats
)
from flashsloth.core.status_detector import detect_platform

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
   
   # 加载缓存的登录状态
   cached_statuses = get_all_cached()
   
   return render_template("accounts.html",
                        grouped=grouped,
                        platforms=platforms,
                        cached_statuses=cached_statuses)

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
       # 更新已有账号：加载原配置，掩码字段保留原值
       existing = conn.execute(
           "SELECT id, config_json FROM platform_accounts WHERE id=? AND user_id=?",
           (edit_id_int, current_user.id)
       ).fetchone()
       if existing:
           orig_cfg = json.loads(existing["config_json"]) if existing["config_json"] else {}
           decrypt_config(orig_cfg)  # 解密原配置
           for k, v in cfg.items():
               if v == MASKED_VALUE and k in orig_cfg:
                   cfg[k] = orig_cfg[k]  # 保留原值
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
   """重定向到账号管理页，由前端模态框处理编辑"""
   return redirect(url_for("accounts"))

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


def _do_playwright_verify(acct: dict, cfg: dict) -> dict:
    """使用 Playwright 验证账号登录状态（共享给 status 和 test 两个端点使用）
    acct: platform_accounts 行 dict
    cfg: 已解密的 config_json dict
    返回结果字典（含 logged_in/status/username_indicators等）
    """
    import re
    cookie = cfg.get("cookie", "")
    site_url = cfg.get("site_url", "")
    platform = acct["platform"]
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
        return result

    # ─── 动态站点：使用 Playwright 全面检测 ─────────
    if not site_url:
        result["logged_in"] = None
        result["status"] = "🔗 未配置站点 URL"
        return result

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
                username_indicators = []
                user_patterns = [
                    rf'{re.escape(account_name)}',
                    rf'欢迎[：:  ].*{re.escape(account_name[:max(2, len(account_name)//2)])}',
                    rf'{re.escape(account_name[:max(2, len(account_name)//2)])}.*欢迎',
                    rf'你好[：: 　].*{re.escape(account_name[:max(2, len(account_name)//2)])}',
                    r'user[=_\\s-][A-Za-z0-9_\\u4e00-\\u9fff]+',
                    r'username[=_\\s-][A-Za-z0-9_\\u4e00-\\u9fff]+',
                    r'nick[=_\\s-][A-Za-z0-9_\\u4e00-\\u9fff]+',
                    r'退出\\s*登录',
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

                # 提取包含用户名的上下文
                user_context = ""
                if username_indicators:
                    for indicator in username_indicators[:3]:
                        idx = body_text.find(indicator)
                        if idx >= 0:
                            start = max(0, idx - 100)
                            end = min(len(body_text), idx + len(indicator) + 100)
                            snippet = body_text[start:end].strip()
                            user_context += f"...{snippet}...\n"

                # ⚠️ 铁律：必须有真实用户信息才算已登录
                is_logged_in = (
                    not redirected_to_login
                    and len(username_indicators) > 0
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
                    reason = "重定向到登录页" if redirected_to_login else "未检测到用户信息(用户名/退出/个人中心等关键词)"
                    if cookie:
                        result["status"] = f"❌ Cookie 已失效（{reason}）"
                    else:
                        result["status"] = f"❌ 未登录（无 Cookie）"

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

    return result


@app.route("/api/accounts/<int:aid>/status")
@login_required
def api_account_status(aid):
    """检查账号登录状态 — 三层检测: 缓存 > API轻量 > Playwright兜底"""
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
    decrypt_config(cfg)
    
    # 第一层：缓存命中且未过期
    update_cache = request.args.get("refresh", "").lower() == "1"
    if not update_cache:
        cached = get_status(aid)
        if cached:
            cached["account_name"] = acct["account_name"]
            cached["is_active"] = bool(acct["is_active"])
            cached["success"] = True
            return jsonify(cached)
    
    # 第二层：API轻量检测
    platform = acct["platform"]
    site_url = cfg.get("site_url", "")
    cookie = cfg.get("cookie", "")
    username = cfg.get("username", "")
    
    if cookie and site_url:
        try:
            api_result = detect_platform(platform, site_url, cookie, username)
            if api_result.get("logged_in"):
                api_result["account_name"] = acct["account_name"]
                api_result["is_active"] = bool(acct["is_active"])
                api_result["success"] = True
                set_status(aid, api_result)
                return jsonify(api_result)
        except Exception as e:
            pass  # 降级到 Playwright
    
    # 第三层：Playwright兜底
    result = _do_playwright_verify(acct, cfg)
    
    # 将 Playwright 结果也写入缓存
    if result.get("success"):
        pw_cache = {
            "logged_in": result.get("logged_in", False),
            "username": "",
            "display_name": result.get("display_name", ""),
            "points": 0,
            "level": "",
            "status": result.get("status", ""),
            "method": "playwright_full",
            "verified_at": datetime.now().isoformat(),
            "page_title": result.get("page_title", ""),
            "username_indicators": result.get("username_indicators", []),
        }
        set_status(aid, pw_cache)
    
    return jsonify(result)

@app.route("/api/accounts/test/<int:aid>", methods=["POST"])
@login_required
def test_account(aid):
   """测试指定账号的连接状态 — 统一使用 Playwright 验证，不再委托给 publisher 的 requests 测试"""
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
   decrypt_config(cfg)  # 解密凭证用于连接测试
   # 复用 api_account_status 的 Playwright 验证逻辑
   result = _do_playwright_verify(acct, cfg)
   return jsonify(result)

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
	"""返回所有平台信息（含登录方法、配置字段 + 登录能力）"""
	from flashsloth.core.publisher import list_publishers
	platforms = list_publishers()
	# 注入从 JSON 读取的登录能力
	import os
	_reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_reports")
	for p in platforms:
		pname = p["name"]
		cap = _load_login_capabilities(pname)
		if cap:
			p["login_capabilities"] = cap
	return jsonify({"success": True, "platforms": platforms})


# ═══════════════════════════════════════════════════
# 登录能力 API — 从 platform_reports JSON 读取
# ═══════════════════════════════════════════════════

# 平台名 → JSON文件名 映射（处理名称不一致）
_PLATFORM_CAP_MAP = {
    "wechat": "wechat_mp",
    "xianyu_v2": "xianyu",
    # 其他平台同名为：csdn, zhihu, bilibili, juejin, oshwhub, xianyu
}

_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_reports")


def _load_login_capabilities(platform: str) -> dict | None:
    """从 platform_reports 加载指定平台的登录能力数据"""
    json_name = _PLATFORM_CAP_MAP.get(platform, platform)
    report_path = os.path.join(_REPORTS_DIR, f"{json_name}_login_capabilities.json")
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


@app.route("/api/platform/<platform>/login-capabilities")
@login_required
def api_platform_login_capabilities(platform):
	"""返回指定平台的登录能力"""
	cap = _load_login_capabilities(platform)
	if cap:
		return jsonify({"success": True, "platform": platform, "source": "json", **cap})
	from flashsloth.core.publisher import list_login_methods
	methods = list_login_methods(platform)
	if methods:
		return jsonify({
			"success": True, "platform": platform, "source": "publisher",
			"login_methods": methods,
			"note": f"来自 {platform} publisher 的预设登录方式",
		})
	return jsonify({"success": False, "error": f"平台 {platform} 无登录能力数据"})


@app.route("/api/platform/<platform>/login-capabilities/refresh", methods=["POST"])
@login_required
def api_platform_login_capabilities_refresh(platform):
	"""重新探索平台的登录能力（用 Playwright）"""
	# 把平台名映射到 JSON 名
	json_name = _PLATFORM_CAP_MAP.get(platform, platform)
	report_path = os.path.join(_REPORTS_DIR, f"{json_name}_login_capabilities.json")
	login_url_map = {
		"csdn": "https://passport.csdn.net/login",
		"zhihu": "https://www.zhihu.com/signin",
		"bilibili": "https://www.bilibili.com/",
		"juejin": "https://juejin.cn/",
		"wechat": "https://mp.weixin.qq.com/",
		"wechat_mp": "https://mp.weixin.qq.com/",
		"oshwhub": "https://passport.jlc.com/login",
		"xianyu": "https://www.goofish.com/",
		"xianyu_v2": "https://www.goofish.com/",
	}
	url = login_url_map.get(platform) or login_url_map.get(json_name)
	if not url:
		return jsonify({"success": False, "error": f"未知登录地址，请先通过 Playwright 探索或提供 site_url"})

	try:
		from playwright.sync_api import sync_playwright
		import base64
		from datetime import datetime, timezone

		with sync_playwright() as pw:
			browser = pw.chromium.launch(
				headless=True,
				args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
			)
			ctx = browser.new_context(
				user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
				viewport={"width": 1920, "height": 1080},
				locale="zh-CN",
			)
			page = ctx.new_page()
			try:
				page.goto(url, wait_until="domcontentloaded", timeout=30000)
				page.wait_for_timeout(5000)
				# 尝试点登录按钮
				login_btn = page.query_selector(
					'button:has-text("登录"), a:has-text("登录"), '
					'[class*="login"] button, .login-btn'
				)
				if login_btn:
					try: login_btn.click(); page.wait_for_timeout(3000)
					except: pass
				# 检测方法
				from explore_login_capabilities import detect_login_methods
				methods, raw = detect_login_methods(page)
				note_methods = [m["label"] for m in methods if m.get("detected")]
				if raw.get("third_party_providers"):
					note_methods.append(f"第三方({','.join(raw['third_party_providers'])})")
				result = {
					"platform": platform,
					"explored_at": datetime.now(timezone.utc).isoformat(),
					"login_url": url,
					"login_methods": methods,
					"note": f"{platform}登录页支持{'/'.join(note_methods)}",
					"raw_detection": raw,
				}
				os.makedirs(_REPORTS_DIR, exist_ok=True)
				with open(report_path, "w", encoding="utf-8") as f:
					json.dump(result, f, ensure_ascii=False, indent=2)
			except Exception as e:
				return jsonify({"success": False, "error": f"探索异常: {str(e)[:200]}"})
			finally:
				page.close(); ctx.close(); browser.close()

		return jsonify({
			"success": True, "platform": platform, "message": "登录能力已重新探索",
			"login_methods": [m["method"] for m in methods if m.get("detected")],
		})
	except Exception as e:
		return jsonify({"success": False, "error": f"Playwright 初始化异常: {str(e)[:200]}"})


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

	elif platform in ("xianyu", "xianyu_v2"):
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu"):
		from plugins.generic_login import get_generic_login, close_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			method = data.get("method", "password")
			if method == "phone":
				phone = data.get("phone", "")
				result = inst.phone_login(platform, phone, site_url)
			else:
				result = inst.login(platform, username, password, site_url)
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

	elif platform in ("xianyu", "xianyu_v2"):
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu"):
		from plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			result = inst.submit_captcha_and_login(platform)
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

	elif platform in ("xianyu", "xianyu_v2"):
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu"):
		from plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			inst = get_generic_login(f"generic_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	return jsonify({"success": False, "error": f"平台 {platform} 不支持截图"})


# ═══════════════════════════════════════════════════
# 统一 QR 码扫码登录 API
# ═══════════════════════════════════════════════════
_qr_login_sessions: dict[str, dict] = {}
_qr_login_locks: dict[str, threading.Lock] = {}

def _get_qr_lock(session_id: str) -> threading.Lock:
	if session_id not in _qr_login_locks:
		_qr_login_locks[session_id] = threading.Lock()
	return _qr_login_locks[session_id]


@app.route("/api/login/qrcode/<platform>/start", methods=["POST"])
@login_required
def api_qrcode_login_start(platform):
	"""启动 QR 码扫码登录 — Playwright 打开平台登录页，返回截图/QR码"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)
	site_url = data.get("site_url", "")

	sess_id = f"qrcode_{current_user.id}_{platform}_{int(time.time())}"
	lock = _get_qr_lock(sess_id)

	try:
		from playwright.sync_api import sync_playwright

		with lock:
			with sync_playwright() as pw:
				browser = pw.chromium.launch(
					headless=True,
					args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
				)
				ctx = browser.new_context(
					user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
					viewport={"width": 1280, "height": 800}, locale="zh-CN",
				)
				page = ctx.new_page()

				# 导航到平台登录页
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

				try:
					page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
					page.wait_for_timeout(3000)
				except Exception as e:
					page.screenshot(path="/tmp/qrcode_login_error.png")
					return jsonify({"success": False, "error": f"无法打开登录页: {str(e)[:80]}"})

				# 获取页面标题和截图
				page_title = page.title()
				import base64
				img_b64 = base64.b64encode(page.screenshot(type="png", full_page=False)).decode()

				# 保存会话
				_qr_login_sessions[sess_id] = {
					"platform": platform,
					"browser": browser,
					"context": ctx,
					"page": page,
					"created_at": time.time(),
					"status": "waiting",
					"user_id": current_user.id,
					"account_id": aid,
					"cookies": "",
					"error": "",
				}

				return jsonify({
					"success": True,
					"session_id": sess_id,
					"image": img_b64,
					"page_title": page_title,
					"message": "请查看页面截图，扫码/登录后系统将自动捕获 Cookie",
				})

	except Exception as e:
		return jsonify({"success": False, "error": f"QR 码登录启动异常: {str(e)[:100]}"})


@app.route("/api/login/qrcode/<platform>/poll/<session_id>")
@login_required
def api_qrcode_login_poll(platform, session_id):
	"""轮询 QR 码/截图登录状态"""
	sess = _qr_login_sessions.get(session_id)
	if not sess:
		return jsonify({"success": False, "error": "会话已过期或不存在", "status": "expired"})

	if sess["user_id"] != current_user.id:
		return jsonify({"success": False, "error": "无权限", "status": "forbidden"})

	lock = _get_qr_lock(session_id)
	with lock:
		page = sess.get("page")
		ctx = sess.get("context")
		if not page or not ctx:
			return jsonify({"success": False, "error": "浏览器已关闭", "status": "closed"})

		try:
			# 刷新截图
			screenshot_b64 = ""
			try:
				import base64
				screenshot_b64 = base64.b64encode(page.screenshot(type="png", full_page=False)).decode()
			except:
				pass

			# 检查 Cookie
			cookies = ctx.cookies()
			all_cookies_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

			# 判断登录态
			current_url = page.url.lower()
			login_keywords = ["login", "signin", "passport", "oauth", "logon"]
			on_login_page = any(kw in current_url for kw in login_keywords)
			has_auth_cookies = any(
				kw in c["name"].lower()
				for c in cookies
				for kw in ["auth", "token", "sid", "session", "login", "passport", "uid", "userid", "key"]
			)

			body_text = ""
			try:
				body_text = page.inner_text("body")[:500]
			except:
				pass

			if has_auth_cookies and not on_login_page and len(cookies) > 2:
				sess["status"] = "logged_in"
				sess["cookies"] = all_cookies_str
				aid = sess.get("account_id")
				if aid:
					_save_cookie_to_account(aid, all_cookies_str)
				return jsonify({
					"success": True,
					"status": "logged_in",
					"cookies": all_cookies_str,
					"image": screenshot_b64,
					"message": "✅ 登录成功！Cookie 已自动获取",
				})
			elif on_login_page:
				return jsonify({
					"success": True,
					"status": "waiting",
					"image": screenshot_b64,
					"url": page.url[:100],
					"page_preview": body_text[:300],
					"message": "🔍 请查看截图，在浏览器中完成登录",
				})
			else:
				return jsonify({
					"success": True,
					"status": "unknown",
					"image": screenshot_b64,
					"cookies_count": len(cookies),
					"page_preview": body_text[:300],
					"message": "⏳ 等待登录完成...",
				})

		except Exception as e:
			return jsonify({"success": False, "error": f"轮询异常: {str(e)[:80]}", "status": "error"})


@app.route("/api/login/qrcode/<platform>/close/<session_id>", methods=["POST"])
@login_required
def api_qrcode_login_close(platform, session_id):
	"""关闭 QR 码登录浏览器会话"""
	sess = _qr_login_sessions.pop(session_id, None)
	if sess:
		lock = _get_qr_lock(session_id)
		with lock:
			try:
				page = sess.get("page")
				if page:
					page.close()
				ctx = sess.get("context")
				if ctx:
					ctx.close()
				browser = sess.get("browser")
				if browser:
					browser.close()
			except:
				pass
	return jsonify({"success": True})


# ═══════════════════════════════════════════════════
# 登录方式演示/说明数据 API
# ═══════════════════════════════════════════════════
LOGIN_METHOD_DEMOS = {
	"password": {
		"title": "🔑 密码登录流程",
		"steps": [
			"① 输入该平台的用户名和密码",
			"② 点击「开始浏览器登录」— 系统在后台打开浏览器",
			"③ 如果出现验证码，查看截图后点击「点验证码并登录」",
			"④ 登录成功后 Cookie 自动保存，无需手动粘贴",
		],
		"note": "适合大多数论坛和博客平台，如 amobbs、mydigit、CSDN",
	},
	"qrcode": {
		"title": "📱 扫码登录流程",
		"steps": [
			"① 选择「扫码登录」方式",
			"② 点击「生成二维码」— 系统打开平台登录页并截图",
			"③ 截图中会显示二维码 / 扫码入口",
			"④ 用手机 App（微信/淘宝/论坛App等）扫码",
			"⑤ 系统自动检测到登录成功，Cookie 自动保存",
		],
		"note": "适合支持扫码登录的平台，如微信公众号、淘宝、B站等",
	},
	"cookie": {
		"title": "🍪 Cookie 粘贴（备选方案）",
		"steps": [
			"① 在浏览器中手动登录该平台",
			"② 打开 F12 → Application → Cookies → 找到该站点",
			"③ 复制所有 Cookie 字符串（或导出为 Netscape 格式）",
			"④ 粘贴到 Cookie 输入框中并保存",
		],
		"note": "Cookie 模式下需要手动续期，建议作为密码登录的备选方案",
	},
	"phone": {
		"title": "📞 手机验证码登录",
		"steps": [
			"① 选择「手机验证码登录」方式",
			"② 输入手机号码",
			"③ 点击「发送验证码」— 系统通过 Playwright 在登录页自动发送",
			"④ 查看截图中的验证码输入框，填入收到的验证码",
			"⑤ 提交后 Cookie 自动保存",
		],
		"note": "适用于支持手机号+验证码登录的平台，如知乎、掘金等",
	},
}


@app.route("/api/login/method-demo/<method>")
@login_required
def api_login_method_demo(method):
	"""返回指定登录方式的演示/说明数据"""
	demo = LOGIN_METHOD_DEMOS.get(method)
	if not demo:
		return jsonify({"success": False, "error": "未知登录方式"})
	return jsonify({"success": True, "demo": demo})


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

	elif platform in ("xianyu", "xianyu_v2"):
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu"):
		from plugins.generic_login import close_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			close_generic_login(sess_id)
			return jsonify({"success": True})

	return jsonify({"success": False, "error": f"平台 {platform} 不支持浏览器登录"})


def _save_cookie_to_account(aid: int, cookie_str: str):
    """保存 Cookie 到账号配置（加密后存储）"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    if acct:
        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        cfg["cookie"] = cookie_str
        encrypt_config(cfg)  # 🔐 加密后再存储
        conn.execute(
            "UPDATE platform_accounts SET config_json=? WHERE id=?",
            (json.dumps(cfg), aid)
        )
        conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════
# 状态检测缓存 API
# ═══════════════════════════════════════════════════

@app.route("/api/accounts/cache/stats")
@login_required
def api_cache_stats():
    """返回缓存统计信息"""
    return jsonify({
        "success": True,
        "stats": get_cache_stats()
    })


@app.route("/api/accounts/cache/flush", methods=["POST"])
@login_required
def api_cache_flush():
    """清除所有状态缓存"""
    # 清除数据库中的 last_status_check
    conn = get_db()
    conn.execute("UPDATE platform_accounts SET status='', last_status_check='' WHERE user_id=?", (current_user.id,))
    conn.commit()
    conn.close()
    # 清除缓存文件（重启进程会让内存缓存失效）
    cache_db = os.path.join(os.path.dirname(os.path.dirname(__file__)), "status_cache.db")
    try:
        if os.path.exists(cache_db):
            os.remove(cache_db)
    except Exception:
        pass
    return jsonify({"success": True, "message": "所有缓存已清除"})


@app.route("/api/accounts/batch/refresh", methods=["POST"])
@login_required
def api_accounts_batch_refresh():
    """批量后台刷新所有活跃账号的状态（异步）"""
    conn = get_db()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? AND is_active=1",
        (current_user.id,)
    ).fetchall()
    conn.close()
    
    if not accounts:
        return jsonify({"success": True, "message": "没有活跃账号", "refreshed": 0})
    
    from flashsloth.core.status_detector import PLATFORM_DETECTORS
    
    refreshed = 0
    errors = []
    for acct in accounts:
        acct = dict(acct)
        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        try:
            from flashsloth.core.credential_crypto import decrypt_config
            decrypt_config(cfg)
        except Exception:
            pass
        
        platform = acct["platform"]
        site_url = cfg.get("site_url", "")
        cookie = cfg.get("cookie", "")
        username = cfg.get("username", "")
        
        # 只对支持API轻量检测的平台做批量刷新
        if platform in PLATFORM_DETECTORS and cookie and site_url:
            try:
                api_result = detect_platform(platform, site_url, cookie, username)
                if api_result.get("logged_in"):
                    api_result["account_name"] = acct["account_name"]
                    set_status(acct["id"], api_result)
                    refreshed += 1
                else:
                    # 登录失败也缓存，避免频繁重试
                    api_result["account_name"] = acct["account_name"]
                    api_result["success"] = False
                    set_status(acct["id"], api_result)
                    refreshed += 1
            except Exception as e:
                errors.append(f"{acct['account_name']}: {str(e)[:80]}")
        else:
            # 不支持API轻量的平台，标记为未缓存
            pass
    
    return jsonify({
        "success": True,
        "refreshed": refreshed,
        "total": len(accounts),
        "errors": errors[:5],
        "message": f"已刷新 {refreshed}/{len(accounts)} 个账号"
    })
