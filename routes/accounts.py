"""FlashSloth — 账号管理路由
从 admin.py 提取，使用 Blueprint 重构"""
from flashsloth.routes._app import app


import json
import os
import re
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
from flashsloth.core.status_detector import detect_platform, PLATFORM_DETECTORS
from flashsloth.core.deployer import list_deployers

# ─── Discuz 系平台集合（登录流程相同，仅 site_url 不同）───
DISCUZ_PLATFORMS = {"amobbs", "discuz", "mydigit"}

# ─── 平台账号管理 ──────────────────────────────
@app.route("/accounts")
@login_required
def accounts():
   conn = get_db()
   accounts = conn.execute(
       "SELECT * FROM platform_accounts WHERE user_id=? ORDER BY platform, created_at",
       (current_user.id,)
   ).fetchall()
   # 加载部署配置和日志（内联到 #deploy 区块）
   deploy_configs = conn.execute(
       "SELECT * FROM deployer_configs WHERE user_id=? ORDER BY created_at DESC",
       (current_user.id,)
   ).fetchall()
   deploy_logs = conn.execute(
       "SELECT * FROM deploy_log ORDER BY created_at DESC LIMIT 20"
   ).fetchall()
   conn.close()
   platforms = list_publishers()
   # 按平台分组
   grouped = {}
   for a in accounts:
       grouped.setdefault(a["platform"], []).append(dict(a))
   
   # 加载缓存的登录状态
   cached_statuses = get_all_cached()
   deployer_list = list_deployers()
   
   return render_template("accounts.html",
                        grouped=grouped,
                        platforms=platforms,
                        cached_statuses=cached_statuses,
                        deployers=deployer_list,
                        configs=deploy_configs,
                        logs=deploy_logs)

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


# ─── 批量操作 API ────────────────────────────────
@app.route("/api/accounts/batch/toggle", methods=["POST"])
@login_required
def api_accounts_batch_toggle():
    """批量启用/禁用账号"""
    data = request.get_json() or {}
    ids = data.get("ids", [])
    enable = data.get("enable", True)
    if not ids or not isinstance(ids, list):
        return jsonify({"success": False, "error": "请选择至少一个账号"})
    conn = get_db()
    placeholders = ",".join("?" for _ in ids)
    params = [1 if enable else 0] + ids + [current_user.id]
    conn.execute(
        f"UPDATE platform_accounts SET is_active=? WHERE id IN ({placeholders}) AND user_id=?",
        params
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"已{'启用' if enable else '禁用'} {len(ids)} 个账号"})


@app.route("/api/accounts/batch/delete", methods=["POST"])
@login_required
def api_accounts_batch_delete():
    """批量删除账号"""
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids or not isinstance(ids, list):
        return jsonify({"success": False, "error": "请选择至少一个账号"})
    conn = get_db()
    placeholders = ",".join("?" for _ in ids)
    params = ids + [current_user.id]
    conn.execute(
        f"DELETE FROM platform_accounts WHERE id IN ({placeholders}) AND user_id=?",
        params
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"已删除 {len(ids)} 个账号"})


def _do_playwright_verify(acct: dict, cfg: dict) -> dict:
    """使用 Playwright 验证账号登录状态（共享给 status 和 test 两个端点使用）
    acct: platform_accounts 行 dict
    cfg: 已解密的 config_json dict
    返回结果字典（含 logged_in/status/username_indicators等）
    
    ⚠️ 铁律：必须找到真实的用户登录指示器才返回 logged_in=True。
       account_name 是用户从别名（如 "discuz01"），不是平台用户名，不能作为登录证据。
       必须检测到至少 2 个独立登录指示器（退出/个人中心/用户名上下文等）才能确认。
    """
    import re
    cookie = cfg.get("cookie", "")
    site_url = cfg.get("site_url", "")
    platform = acct["platform"]
    account_name = acct.get("account_name", "")
    # 实际的平台用户名（在 config 中有专门的 username 字段，可能不同于 account_name）
    platform_username = cfg.get("username", "")
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

    # ─── 动态站点：通过子进程调用 Playwright 验证 ────
    # 在独立子进程中运行 Playwright，避免 WSGI 线程的 "Event loop is closed" 问题
    if not site_url:
        result["logged_in"] = None
        result["status"] = "🔗 未配置站点 URL"
        return result

    import subprocess as _sp, os as _os
    
    script_path = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "scripts", "playwright_verify.py")
    if not _os.path.exists(script_path):
        result["status"] = "❌ Playwright 验证脚本不存在"
        return result
    
    try:
        pw_env = _os.environ.copy()
        pw_env["PYTHONPATH"] = f"{_os.path.expanduser('~/.hermes')}:{_os.path.expanduser('~/.hermes/flashsloth')}"
        
        pw_proc = _sp.run(
            [_os.path.expanduser("~/.hermes/flashsloth/venv/bin/python3"), script_path, str(acct["id"])],
            capture_output=True, text=True, timeout=45, env=pw_env,
        )
        
        if pw_proc.returncode != 0:
            result["status"] = f"❌ Playwright 子进程异常: {pw_proc.stderr[:100] if pw_proc.stderr else 'exit ' + str(pw_proc.returncode)}"
            return result
        
        pw_result = json.loads(pw_proc.stdout)
        
        # 将子进程结果合并到当前 result
        for key in ("logged_in", "status", "username_indicators", "username", "display_name",
                    "points", "level", "page_title", "page_url", "page_preview", "error", "success"):
            if key in pw_result:
                result[key] = pw_result[key]
        
        # 页面预览
        if pw_result.get("page_preview"):
            result["page_preview"] = pw_result["page_preview"][:500]
        
        # 确保 is_static 被携带
        result["is_static_site"] = is_static
        
    except _sp.TimeoutExpired:
        result["logged_in"] = False
        result["status"] = "❌ Playwright 验证超时（45秒）"
    except json.JSONDecodeError as e:
        result["logged_in"] = False
        result["status"] = f"❌ Playwright 结果解析失败: {str(e)[:60]}"
    except Exception as e:
        result["logged_in"] = False
        result["status"] = f"❌ Playwright 子进程异常: {str(e)[:100]}"

    return result


@app.route("/api/accounts/<int:aid>/status")
@login_required
def api_account_status(aid):
    """检查账号登录状态 — 三层: 缓存 > API轻量检测 > Playwright兜底"""
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
    
    # 第二层：API轻量检测（仅用于快速检测 Cookie 过期，不作为登录态判定依据）
    # ⚠️ 铁律：API轻量检测不可作为登录态判定依据 — 它对假Cookie可能误报"已登录"
    # 只有当 API 明确检测到"未登录"（重定向到登录页等）时才信任它
    # 任何"已登录"判断必须经过 Playwright 真实浏览器验证
    platform = acct["platform"]
    site_url = cfg.get("site_url", "")
    cookie = cfg.get("cookie", "")
    username_hint = cfg.get("username", "")
    
    if platform in PLATFORM_DETECTORS and cookie and site_url:
        try:
            api_result = detect_platform(platform, site_url, cookie, username_hint)
            
            if api_result.get("logged_in") == False and not api_result.get("_detection_error"):
                # API明确检测到未登录 → 缓存并返回（避免启动浏览器，毫秒级）
                fail_cache = {
                    "logged_in": False,
                    "username": "",
                    "display_name": "",
                    "points": 0,
                    "level": "",
                    "status": api_result.get("status", "❌ Cookie已失效"),
                    "method": "api_lightweight",
                    "verified_at": api_result.get("verified_at", datetime.now().isoformat()),
                    "error": api_result.get("error", "Cookie失效"),
                }
                set_status(aid, fail_cache)
                fail_cache["account_name"] = acct["account_name"]
                fail_cache["is_active"] = bool(acct["is_active"])
                fail_cache["success"] = True
                return jsonify(fail_cache)
        except Exception as e:
            pass  # API检测异常，降级到Playwright
    
    # 第三层：Playwright 真实浏览器验证（兜底）
    result = _do_playwright_verify(acct, cfg)
    result["method"] = "playwright_full"
    
    # 将 Playwright 结果写入缓存
    if result.get("success") or result.get("logged_in") is not None:
        pw_cache = {
            "logged_in": result.get("logged_in", False),
            "username": result.get("username", ""),
            "display_name": result.get("display_name", ""),
            "points": result.get("points", 0),
            "level": result.get("level", ""),
            "status": result.get("status", ""),
            "method": "playwright_full",
            "verified_at": datetime.now().isoformat(),
            "page_title": result.get("page_title", ""),
            "username_indicators": result.get("username_indicators", []),
            "page_preview": result.get("page_preview", ""),
            "page_url": result.get("page_url", ""),
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
   result["method"] = "playwright_test"
   
   # 同时更新状态缓存（测试连接也算一次状态刷新）
   if result.get("success") or result.get("logged_in") is not None:
       cache_data = {
           "logged_in": result.get("logged_in", False),
           "username": result.get("username", ""),
           "display_name": result.get("display_name", ""),
           "points": result.get("points", 0),
           "level": result.get("level", ""),
           "status": result.get("status", ""),
           "method": "playwright_test",
           "verified_at": datetime.now().isoformat(),
           "page_title": result.get("page_title", ""),
           "username_indicators": result.get("username_indicators", []),
           "page_preview": result.get("page_preview", ""),
           "page_url": result.get("page_url", ""),
       }
       set_status(aid, cache_data)
   
   return jsonify(result)

@app.route("/api/accounts/<int:aid>/signin_settings", methods=["POST"])
@login_required
def api_account_signin_settings(aid):
   """保存账号的签到设置（启用/禁用、签到时间、随机偏移）"""
   data = request.get_json() or {}
   signin_enabled = data.get("signin_enabled")
   signin_time = data.get("signin_time")
   random_offset = data.get("random_offset_minutes")
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
   if random_offset is not None:
       # 限制 ±30 分钟
       cfg["random_offset_minutes"] = max(-30, min(30, int(random_offset)))
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





# ─── API 缓存：空搜索缓存 30 秒 ───
_platform_search_cache = {"data": None, "ts": 0}
_PLATFORM_SEARCH_CACHE_TTL = 30  # 秒


@app.route("/api/platforms/search")
@login_required
def api_platforms_search():
	"""模糊搜索平台 — 匹配 name / display_name，动态加载架构类型

	数据来源（覆盖所有已配置平台）：
	1. list_publishers() — 已注册发布器
	2. platform_reports/*_login_capabilities.json — 有登录能力的平台
	3. forum_registry.FORUM_DATA — Discuz! 论坛域名

	异常保护：单个源失败不影响其他源
	缓存：空搜索（q 为空）结果缓存 30 秒
	"""
	from flashsloth.core.publisher import list_publishers
	q = request.args.get("q", "").strip().lower()

	# ─── 空搜索缓存命中 ───
	if not q and _platform_search_cache["data"] is not None:
		if time.time() - _platform_search_cache["ts"] < _PLATFORM_SEARCH_CACHE_TTL:
			return jsonify({"success": True, "results": _platform_search_cache["data"], "total": len(_platform_search_cache["data"])})

	results = []
	seen = set()  # 去重

	# ─── 1. list_publishers() ───
	try:
		publishers = list_publishers()
		for p in publishers:
			name = p["name"]
			display_name = p["display_name"]
			name_lower = name.lower()
			display_lower = display_name.lower()
			if q and q not in name_lower and q not in display_lower:
				continue
			arch = p.get("architecture", "")
			results.append({
				"name": name,
				"display_name": display_name,
				"architecture": arch,
				"config_fields": p.get("config_fields", []),
				"login_methods": p.get("login_methods", []),
			})
			seen.add(name)
	except Exception:
		# 源 1 失败不影响其他源
		pass

	# ─── 2. platform_reports/*_login_capabilities.json ───
	try:
		import glob as _glob
		reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_reports")
		pattern = os.path.join(reports_dir, "*_login_capabilities.json")
		for cap_path in _glob.glob(pattern):
			fname = os.path.basename(cap_path)  # e.g. amobbs_login_capabilities.json
			pname = fname.replace("_login_capabilities.json", "")  # e.g. amobbs
			if pname in seen:
				continue
			if q and q not in pname.lower():
				continue
			# 读取 display_name + note
			try:
				with open(cap_path, "r", encoding="utf-8") as f:
					cap = json.load(f)
			except Exception:
				cap = {}
			display_name = cap.get("platform_name") or cap.get("display_name") or pname.replace("_", " ").title()
			note = cap.get("note", "")
			arch = ""
			if note:
				note_lower = note.lower()
				if "discuz" in note_lower:
					arch = "基于 Discuz! 架构"
			results.append({
				"name": pname,
				"display_name": display_name,
				"architecture": arch,
				"note": note[:80],
				"config_fields": [],
				"login_methods": cap.get("login_methods", []),
			})
			seen.add(pname)
	except Exception:
		# 源 2 失败不影响其他源
		pass

	# ─── 3. forum_registry — 域名级 Discuz 补充 ───
	try:
		from flashsloth.core.forum_registry import FORUM_DATA
		for domain in FORUM_DATA:
			base = domain.split(".")[0]  # amobbs.com → amobbs
			if base in seen:
				continue
			if q and q not in base.lower():
				continue
			display_name = f"{base.title()} 论坛 ({domain})"
			results.append({
				"name": base,
				"display_name": display_name,
				"architecture": "",
				"config_fields": [],
				"login_methods": [],
			})
			seen.add(base)
	except Exception:
		# 源 3 失败不影响其他源
		pass

	# 按 display_name 排序
	results.sort(key=lambda x: x["display_name"])

	# ─── 空搜索写入缓存 ───
	if not q:
		_platform_search_cache["data"] = results
		_platform_search_cache["ts"] = time.time()

	return jsonify({"success": True, "results": results, "total": len(results)})


# ═══════════════════════════════════════════════════
# 登录能力 API — 从 platform_reports JSON 读取
# ═══════════════════════════════════════════════════

# 平台名 → JSON文件名 映射（处理名称不一致）
_PLATFORM_CAP_MAP = {
    "wechat": "wechat_mp",
    "xianyu_v2": "xianyu",
    "xianyu_sidecar": "xianyu",
    "xianyu_auto_reply": "xianyu",
    "xianyu_products": "xianyu",
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


# OAuth provider 图标映射
_OAUTH_ICON_MAP = {
    "qq": "🐧",
    "weibo": "📣",
    "wechat_oauth": "💬",
    "github": "🐙",
    "google": "🔵",
    "apple": "🍎",
}

# OAuth provider 标签映射
_OAUTH_LABEL_MAP = {
    "qq": "QQ登录",
    "weibo": "微博登录",
    "wechat_oauth": "微信登录",
    "github": "GitHub登录",
    "google": "Google登录",
    "apple": "Apple登录",
}


def _extract_captcha_info(raw_detection: dict | None) -> dict:
    """从 raw_detection 中提取验证码信息"""
    if not raw_detection:
        return {"has_captcha": False, "types": [], "note": ""}
    has_captcha = raw_detection.get("has_captcha", False)
    captcha_type = raw_detection.get("captcha_type")
    captcha_note = raw_detection.get("captcha_description") or raw_detection.get("captcha_note") or ""
    return {
        "has_captcha": bool(has_captcha),
        "types": [captcha_type] if captcha_type else [],
        "note": captcha_note,
    }


def _enhance_login_methods(methods: list, raw_detection: dict | None) -> list:
    """增强登录方法列表：添加 fields、展开 providers、添加 captcha 信息"""
    enhanced = []
    captcha_info = _extract_captcha_info(raw_detection)
    for m in methods:
        if not m.get("detected"):
            continue
        method = m["method"]
        entry = dict(m)  # shallow copy to preserve original fields
        if method == "password":
            entry["fields"] = ["username", "password"]
            entry["captcha"] = {
                "has_captcha": captcha_info["has_captcha"],
                "type": captcha_info["types"][0] if captcha_info["types"] else None,
                "description": captcha_info["note"] or None,
            }
        elif method == "phone":
            entry["fields"] = ["phone"]
        elif method == "qrcode":
            # 保留原有的 sub_types 数组
            pass
        elif method == "oauth":
            providers = m.get("providers", [])
            entry["providers"] = [
                {
                    "id": pid,
                    "label": _OAUTH_LABEL_MAP.get(pid, f"{pid}登录"),
                    "icon": _OAUTH_ICON_MAP.get(pid, "🔗"),
                }
                for pid in providers
            ]
        elif method == "cookie":
            entry["fields"] = ["cookie"]
        enhanced.append(entry)
    return enhanced


@app.route("/api/platform/<platform>/login-capabilities")
@login_required
def api_platform_login_capabilities(platform):
    """返回指定平台的登录能力（增强版：含 site_url_default、OAuth providers、验证码信息）"""
    cap = _load_login_capabilities(platform)
    if cap:
        from flashsloth.core.publisher import _registry as _publisher_registry
        cls = _publisher_registry.get(platform)
        guide = getattr(cls, 'guide', None) if cls else None

        login_url = cap.get("login_url", "")
        raw_detection = cap.get("raw_detection")
        methods = cap.get("login_methods", [])

        enhanced_methods = _enhance_login_methods(methods, raw_detection)
        captcha_info = _extract_captcha_info(raw_detection)

        return jsonify({
            "success": True,
            "platform": platform,
            "login_url": login_url,
            "site_url_default": login_url if login_url.startswith("http") else "",
            "login_methods": enhanced_methods,
            "captcha_info": captcha_info,
            "source": "json",
            "guide": guide,
        })

    from flashsloth.core.publisher import _registry as _publisher_registry, list_login_methods
    methods = list_login_methods(platform)
    cls = _publisher_registry.get(platform)
    guide = getattr(cls, 'guide', None) if cls else None
    if methods:
        return jsonify({
            "success": True, "platform": platform, "source": "publisher",
            "login_methods": methods,
            "guide": guide,
            "note": f"来自 {platform} publisher 的预设登录方式",
        })
    return jsonify({"success": False, "error": f"平台 {platform} 无登录能力数据"})


@app.route("/api/platform/<platform>/login-capabilities/refresh", methods=["POST"])
@login_required
def api_platform_login_capabilities_refresh(platform):
	"""重新探索平台的登录能力（用 Playwright）
	
	铁律#12：优先使用 POST body 中的 site_url，避免硬编码。
	"""
	# 把平台名映射到 JSON 名
	json_name = _PLATFORM_CAP_MAP.get(platform, platform)
	report_path = os.path.join(_REPORTS_DIR, f"{json_name}_login_capabilities.json")
	
	# 🔥 铁律#12：先接受 post body 中动态 site_url
	data = request.get_json(silent=True) or {}
	site_url_from_body = str(data.get("site_url", "") or "").strip()
	# 如果 site_url 是纯域名，自动补上 https://
	if site_url_from_body and not site_url_from_body.startswith(("http://", "https://")):
		site_url_from_body = "https://" + site_url_from_body
	
	# 硬编码兜底（仅当无动态 site_url 时）
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
		"xianyu_sidecar": "https://www.goofish.com/",
		"xianyu_auto_reply": "https://www.goofish.com/",
		"xianyu_products": "https://www.goofish.com/",
	}
	# 优先级：POST body site_url > 硬编码映射 > 失败
	url = site_url_from_body or login_url_map.get(platform) or login_url_map.get(json_name)
	if not url:
		return jsonify({"success": False, "error": f"未知登录地址，请先通过 Playwright 探索或提供 site_url"})

	try:
		from flashsloth.core.browser_engine import BrowserEngine
		import base64
		from datetime import datetime, timezone

		_engine = BrowserEngine.get_instance()
		_ctx = _engine.create_isolated_context()
		if not _ctx:
			# 引擎未就绪 → 启动
			_engine.start()
			_ctx = _engine.create_isolated_context()
			if not _ctx:
				raise RuntimeError("无法启动 Playwright 浏览器引擎")
		page = _ctx.new_page()

		page.goto(url, wait_until="domcontentloaded", timeout=30000)
		page.wait_for_timeout(3000)

		# 截图
		screenshot_dir = os.path.join(_REPORTS_DIR, "screenshots")
		os.makedirs(screenshot_dir, exist_ok=True)
		screenshot_path = os.path.join(screenshot_dir, f"{json_name}_login.png")
		page.screenshot(path=screenshot_path, full_page=False)
		with open(screenshot_path, "rb") as f:
			screenshot_b64 = base64.b64encode(f.read()).decode("utf-8")

		# 检测登录方式
		body_text = page.inner_text("body")[:3000]
		page_html = page.content()
		page_url = page.url
		page_title = page.title()

		has_password = page.query_selector("input[type='password']") is not None
		has_phone = bool(re.search(r"手机号|电话号码|phone|mobile", body_text, re.I))
		has_code_btn = bool(re.search(r"获取验证码|发送验证码|get.*code|send.*code", body_text, re.I))
		has_qrcode = page.query_selector("img[src*='qrcode'], canvas[class*='qrcode'], div[class*='qrcode']") is not None
		has_wechat = bool(re.search(r"微信|wechat|weixin", body_text, re.I)) or page.query_selector("img[alt*='wechat'], i[class*='wechat']") is not None
		has_app_qr = bool(re.search(r"APP扫码|APP.*扫码|客户端扫码", body_text, re.I))
		has_oauth = page.query_selector("[class*='oauth'], [class*='third'], [class*='social'], a[href*='qq'], a[href*='weibo'], a[href*='github']") is not None

		# 检测第三方提供商
		third_providers = []
		for prov, patterns in [("qq", r"qq\.com|QQ"), ("weibo", r"weibo\.com|微博"),
								("github", r"github\.com|GitHub"), ("google", r"google|Google"),
								("wechat_oauth", r"微信登录|wechat")]:
			if re.search(patterns, page_html, re.I):
				third_providers.append(prov)
		third_providers = list(dict.fromkeys(third_providers))  # 去重保序

		# 构建 login_methods
		methods = []
		if has_password:
			methods.append({"method": "password", "label": "账号密码登录", "detected": True, "selector": "input[type='password']"})

		phone_detected = has_phone and has_code_btn
		if phone_detected:
			methods.append({"method": "phone", "label": "手机验证码登录", "detected": True, "selector": "input[type='tel']"})

		qrcode_sub_types = []
		if has_wechat:
			qrcode_sub_types.append({"id": "wechat", "label": "微信扫码", "detected": True})
		if has_app_qr:
			qrcode_sub_types.append({"id": "app", "label": "APP扫码", "detected": True})
		if has_qrcode or qrcode_sub_types:
			qrcode_sub_types = qrcode_sub_types or [{"id": "default", "label": "二维码登录", "detected": True}]
			methods.append({"method": "qrcode", "label": "扫码登录", "detected": True, "sub_types": qrcode_sub_types, "selector": "img[src*='qrcode']"})

		if third_providers or has_oauth:
			methods.append({"method": "oauth", "label": "第三方账号登录", "detected": True, "providers": third_providers or ["wechat_oauth", "qq", "weibo"]})

		methods.append({"method": "cookie", "label": "Cookie粘贴", "detected": True})

		# 构建备注
		detected_labels = [m["label"] for m in methods if m.get("detected") and m["method"] != "cookie"]
		note_parts = [f"{json_name}登录页支持"]
		note_parts.append("/".join(detected_labels))
		if third_providers:
			note_parts.append(f"/第三方({','.join(third_providers)})")
		note = "".join(note_parts)

		cap_data = {
			"platform": json_name,
			"explored_at": datetime.now(timezone.utc).isoformat(),
			"login_url": url,
			"login_methods": methods,
			"note": note,
			"raw_detection": {
				"has_password_input": has_password,
				"has_phone_input": has_phone,
				"has_code_button": has_code_btn,
				"has_qrcode_img": has_qrcode,
				"has_wechat": has_wechat,
				"has_app_qr": has_app_qr,
				"third_party_providers": third_providers,
				"page_title": page_title,
				"page_url": page_url,
			},
			"error": None,
			"screenshot": screenshot_path,
		}

		# 保存 JSON
		with open(report_path, "w", encoding="utf-8") as f:
			json.dump(cap_data, f, ensure_ascii=False, indent=2)

		page.close()
		_ctx.close()

		return jsonify({
			"success": True, "platform": platform, "message": "登录能力已重新探索",
			"login_methods": [m["method"] for m in methods if m.get("detected")],
			"capabilities": cap_data,
		})
	except Exception as e:
		# 清理 Playwright 资源
		try:
			if 'page' in dir(): page.close()
			if '_ctx' in dir(): _ctx.close()
		except: pass
		return jsonify({"success": False, "error": f"Playwright 检测异常: {str(e)[:200]}"})


# ═══════════════════════════════════════════════════
# 扫码登录方式查询 API
# ═══════════════════════════════════════════════════
@app.route("/api/login/scan-methods/<platform>")
@login_required
def api_login_scan_methods(platform):
    """返回指定平台支持的扫码登录方式列表
    
    数据来源：core/credential_provider.PLATFORM_SCAN_INFO
    每个平台可有多重扫码方式（如闲鱼：闲鱼App扫码 / 淘宝App扫码）
    """
    from flashsloth.core.credential_provider import PLATFORM_SCAN_INFO
    info = PLATFORM_SCAN_INFO.get(platform)
    if not info:
        return jsonify({
            "success": False,
            "error": f"平台 {platform} 无扫码登录信息",
        })
    methods = info.get("scan_methods", [])
    return jsonify({
        "success": True,
        "platform": platform,
        "login_url": info.get("login_url", ""),
        "methods": methods,
    })


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

	if platform in DISCUZ_PLATFORMS:
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id, site_url=site_url)
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu", "wordpress"):
		from flashsloth.plugins.generic_login import get_generic_login, close_generic_login
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

	if platform in DISCUZ_PLATFORMS:
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id)
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu", "wordpress"):
		from flashsloth.plugins.generic_login import get_generic_login
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
	if platform in DISCUZ_PLATFORMS:
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_discuz_login(f"user_{current_user.id}_{platform}")
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu", "wordpress"):
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			inst = get_generic_login(f"generic_{current_user.id}")
			return jsonify({"success": True, "image": inst.take_screenshot()})

	return jsonify({"success": False, "error": f"平台 {platform} 不支持截图"})


@app.route("/api/platform/<platform>/login/submit_captcha", methods=["POST"])
@login_required
def api_platform_login_submit_captcha(platform):
	"""统一登录：提交手动输入的验证码"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)
	captcha_code = data.get("captcha_code", "")

	if not captcha_code:
		return jsonify({"success": False, "error": "请输入验证码"})

	if platform in DISCUZ_PLATFORMS:
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id)
			# 提交文本验证码 — 填入代码，点击边框核验，再提交登录
			result = inst.submit_text_captcha(captcha_code)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif platform in ("xianyu", "xianyu_v2"):
		return jsonify({"success": False, "error": "闲鱼不支持手动验证码输入，请使用扫码登录"})

	elif platform == "oshwhub":
		from flashsloth.routes.browser_login import _get_oshwhub_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}"
			inst = _get_oshwhub_login(sess_id)
			result = inst.submit_text_captcha(captcha_code)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu", "wordpress"):
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			result = inst.submit_text_captcha(captcha_code, platform)
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持验证码提交"})


@app.route("/api/platform/<platform>/login/poll_result", methods=["POST"])
@login_required
def api_platform_login_poll(platform):
	"""轮询登录结果（验证码提交后的异步登录流程）"""
	data = request.get_json() or {}
	aid = data.get("account_id", 0)

	if platform in DISCUZ_PLATFORMS:
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			inst = _get_discuz_login(sess_id)
			# 检查当前登录状态
			cookies = inst.get_cookies()
			if cookies:
				try:
					page_url = inst.page.url if inst.page else ""
					is_still_login = "login" not in page_url.lower()
				except:
					is_still_login = False

				if is_still_login:
					if aid:
						_save_cookie_to_account(aid, cookies)
					return jsonify({"logged_in": True, "cookies": cookies})

			# 检查是否需要新验证码
			try:
				screenshot = inst.take_screenshot()
				page_content = inst.page.content() if inst.page else ""
				if "验证码" in page_content or "seccode" in page_content:
					return jsonify({
						"needs_captcha": True,
						"image": screenshot,
						"error": "需要新验证码",
					})
			except:
				pass

			return jsonify({"running": True, "message": "登录进行中..."})

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu", "wordpress"):
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"generic_{current_user.id}"
			inst = get_generic_login(sess_id)
			result = inst.poll_login_result()
			if result.get("logged_in") and result.get("cookies") and aid:
				_save_cookie_to_account(aid, result["cookies"])
			return jsonify(result)

	return jsonify({"success": False, "error": f"平台 {platform} 不支持轮询"})


@app.route("/api/platform/<platform>/login/refresh_captcha", methods=["POST"])
@login_required
def api_platform_login_refresh_captcha(platform):
	"""刷新验证码图片"""
	if platform in DISCUZ_PLATFORMS:
		from flashsloth.routes.browser_login import _get_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			inst = _get_discuz_login(f"user_{current_user.id}_{platform}")
			screenshot = inst.take_screenshot()
			return jsonify({"success": True, "image": screenshot})
	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu", "wordpress"):
		from flashsloth.plugins.generic_login import get_generic_login
		lock = _get_login_lock(platform)
		with lock:
			inst = get_generic_login(f"generic_{current_user.id}")
			screenshot = inst.take_screenshot()
			return jsonify({"success": True, "image": screenshot})
	return jsonify({"success": False, "error": "不支持的平台"})


@app.route("/api/platform/<platform>/login/auto_captcha", methods=["POST"])
@login_required
def api_platform_login_auto_captcha(platform):
	"""自动识别验证码（预留：ttshitu/2captcha）"""
	from flashsloth.core.captcha_handler import get_handler
	handler = get_handler()
	# 先尝试截图
	try:
		if platform in DISCUZ_PLATFORMS:
			from flashsloth.routes.browser_login import _get_discuz_login
			with _get_login_lock(platform):
				inst = _get_discuz_login(f"user_{current_user.id}_{platform}")
				screenshot = inst.take_screenshot()
		else:
			from flashsloth.plugins.generic_login import get_generic_login
			with _get_login_lock(platform):
				inst = get_generic_login(f"generic_{current_user.id}")
				screenshot = inst.take_screenshot()

		if screenshot:
			# 尝试自动识别
			code = handler.auto_solve(screenshot, handler.CaptchaProvider.AUTO_TTSHITU)
			if code:
				return jsonify({"success": True, "code": code})
	except:
		pass
	return jsonify({"success": False, "error": "自动识别暂未配置，请手动输入验证码"})


# ═══════════════════════════════════════════════════
# 统一 QR 码扫码登录 API — 线程安全版
# ═══════════════════════════════════════════════════
# 使用后台线程管理 Playwright 浏览器，避免线程切换问题。
# start → 启动后台线程打开浏览器 → 截图返回 → 线程保持浏览器运行
# poll → 通知后台线程检查登录态 → 返回结果
# close → 通知后台线程关闭浏览器并退出
# ═══════════════════════════════════════════════════
import queue as _qr_queue
import threading as _qr_threading

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
	if platform in DISCUZ_PLATFORMS:
		from flashsloth.routes.browser_login import _close_discuz_login
		lock = _get_login_lock(platform)
		with lock:
			sess_id = f"user_{current_user.id}_{platform}"
			_close_discuz_login(sess_id)
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

	elif platform in ("csdn", "wechat", "bilibili", "juejin", "zhihu", "wordpress"):
		from flashsloth.plugins.generic_login import close_generic_login
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
    """批量后台刷新所有活跃账号的状态（异步）
    
    ⚠️ 铁律：API轻量检测只能用于快速判定"未登录"（重定向到登录页等明确信号）。
    API轻量检测的"已登录"结果不可信任——它对假Cookie/过期Cookie可能误报为已登录。
    批量刷新仅做"状态预检"，不会用Playwright验证。
    如需真实登录态确认，请使用"状态检测"按钮（Playwright全量验证）。
    """
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
    api_passed = 0
    api_failed = 0
    skipped = 0
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
                # ⚠️ 铁律：API轻量检测只能信任"未登录"结果
                # "已登录"结果必须经过Playwright才能确认
                # 这里只缓存API检测结果，不标记为已登录
                if api_result.get("logged_in") == False:
                    # API明确检测到未登录（重定向到登录页等）→ 可信任
                    cache_data = {
                        "logged_in": False,
                        "username": "",
                        "display_name": "",
                        "points": 0,
                        "level": "",
                        "status": "❌ Cookie已失效（API轻量检测）",
                        "method": "api_lightweight",
                        "verified_at": datetime.now().isoformat(),
                        "error": api_result.get("error", "Cookie失效"),
                    }
                    set_status(acct["id"], cache_data)
                    api_failed += 1
                else:
                    # API检测通过 或 无明确判定
                    # → 缓存为"待确认"状态，提示用户点击"状态检测"按钮做Playwright验证
                    cache_data = {
                        "logged_in": None,  # null = 未确认
                        "username": api_result.get("username", ""),
                        "display_name": api_result.get("display_name", ""),
                        "points": api_result.get("points", 0),
                        "level": api_result.get("level", ""),
                        "status": "⏳ 待确认（API轻量检测通过，需要Playwright确认）",
                        "method": "api_lightweight",
                        "verified_at": datetime.now().isoformat(),
                    }
                    set_status(acct["id"], cache_data)
                    api_passed += 1
                refreshed += 1
            except Exception as e:
                errors.append(f"{acct['account_name']}: {str(e)[:80]}")
                skipped += 1
        else:
            # 不支持API轻量的平台，跳过
            skipped += 1
    
    return jsonify({
        "success": True,
        "refreshed": refreshed,
        "total": len(accounts),
        "api_passed": api_passed,
        "api_failed": api_failed,
        "skipped": skipped,
        "errors": errors[:5],
        "message": f"已刷新 {refreshed}/{len(accounts)} 个账号（API通过:{api_passed} API失效:{api_failed} 跳过:{skipped}）"
    })


@app.route("/api/accounts/test-connection", methods=["POST"])
@login_required
def api_test_connection():
    """测试账号连接 — 在保存前验证凭证有效性"""
    try:
        data = request.get_json(silent=True) or {}
        platform = data.get("platform", "")
        if not platform:
            # 尝试从 form-data 读取
            platform = request.form.get("platform", "")
        if not platform:
            return jsonify({"success": False, "error": "缺少平台名"})
        # 从 config 嵌套字段或 cfg_ 前缀字段读取
        config = {}
        nested_config = data.get("config", {})
        if isinstance(nested_config, dict):
            config.update(nested_config)
        # 也检查顶层 cfg_ 前缀字段
        for k, v in data.items():
            if k.startswith("cfg_"):
                config[k[4:]] = v
        # 也检查 form-data 中的 cfg_ 前缀字段
        for k, v in request.form.items():
            if k.startswith("cfg_"):
                config[k[4:]] = v
        # 尝试使用 publisher 的 test_connection
        from flashsloth.core.publisher import _registry as _publisher_registry
        cls = _publisher_registry.get(platform)
        result_data = {}
        if cls and hasattr(cls, 'test_connection') and callable(cls.test_connection):
            try:
                pub = cls(config)
                test_result = pub.test_connection()
                # ⚠️ 统一为 flat 格式（与 test_account() 返回格式一致）
                # discuz publisher 返回 {"success": True, "status": "已登录 — ...", ...}
                # 而前端 testConnectionAdd() 需要 data.logged_in / data.username / data.status
                result_data = {
                    "success": test_result.get("success", False),
                    "logged_in": test_result.get("success", False)
                        and ("已登录" in test_result.get("status", "") or test_result.get("status", "").startswith("✅")),
                    "status": test_result.get("status", "⏳ 未知"),
                    "username": test_result.get("username", "") or test_result.get("display_name", ""),
                    "platform": platform,
                    "error": test_result.get("error", ""),
                }
                return jsonify(result_data)
            except Exception as e:
                return jsonify({"success": False, "error": f"连接测试失败: {str(e)[:200]}"})
        # 降级：Cookie + site_url 进行 Playwright 验证（使用独立子进程，避免WSGI线程问题）
        cookie = config.get("cookie", data.get("cookie", ""))
        site_url = config.get("site_url", data.get("site_url", ""))
        username = config.get("username", data.get("username", ""))
        if cookie and site_url:
            # 使用子进程运行 Playwright 验证，传参通过 stdin JSON
            import subprocess as _sp, os as _os, sys as _sys
            _pw_env = _os.environ.copy()
            _pw_env["PYTHONPATH"] = f"{_os.path.expanduser('~/.hermes')}:{_os.path.expanduser('~/.hermes/flashsloth')}"
            _pw_script = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "scripts", "playwright_verify_raw.py")
            if _os.path.exists(_pw_script):
                try:
                    _input_json = json.dumps({
                        "cookie": cookie, "site_url": site_url,
                        "username": username, "platform": platform
                    }, ensure_ascii=False)
                    _pw_proc = _sp.run(
                        [_os.path.expanduser("~/.hermes/flashsloth/venv/bin/python3"), _pw_script],
                        capture_output=True, text=True, timeout=45, env=_pw_env,
                        input=_input_json,
                    )
                    if _pw_proc.returncode == 0 and _pw_proc.stdout.strip():
                        pw_result = json.loads(_pw_proc.stdout)
                        # playwright_verify_raw.py 已经返回 flat 格式（含 logged_in / username / status）
                        return jsonify(pw_result)
                except Exception as e:
                    pass  # Playwright 降级失败，兜底返回
            return jsonify({"success": False, "error": "无有效凭证可测试（需要 Cookie 或 账号密码）"})
        return jsonify({"success": False, "error": "需要配置站点 URL 和 Cookie 才能测试连接"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:200]})
