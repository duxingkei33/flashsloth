"""FlashSloth — 账号管理路由：状态检测"""
from flashsloth.routes._app import app
from flask import jsonify, request
from flask_login import login_required, current_user

import json
from datetime import datetime

from flashsloth.core.database import get_db
from flashsloth.core.credential_crypto import decrypt_config
from flashsloth.core.status_cache import get_status, set_status
from flashsloth.core.status_detector import detect_platform, PLATFORM_DETECTORS


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

    script_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "scripts", "playwright_verify.py")
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
