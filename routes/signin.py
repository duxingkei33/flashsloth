"""FlashSloth 签到管理路由模块"""
from flashsloth.routes._app import app

from flask import render_template, request, redirect, url_for, flash, jsonify
import json, concurrent.futures
from datetime import datetime

from flask_login import login_required, current_user
from flashsloth.core.database import get_db

from flashsloth.core.scheduler import scheduler_running, scheduler_stop, start_scheduler

@app.route("/signin")
@login_required
def signin_page():
   """签到页面 — 查看状态 + 手动签到"""
   conn = get_db()

   # 所有账号（含禁用）
   accounts = conn.execute(
       "SELECT * FROM platform_accounts ORDER BY is_active DESC, platform, account_name"
   ).fetchall()

   # 最近签到记录
   logs = conn.execute(
       "SELECT * FROM signin_log ORDER BY created_at DESC LIMIT 50"
   ).fetchall()

   # 统计
   today = datetime.now().strftime("%Y-%m-%d")
   today_count = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=1 AND already_signed=0",
        (today,)
    ).fetchone()[0]
   today_total = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=1",
        (today,)
    ).fetchone()[0]

   # 今日成功（同 today_total — distinct 账号今日签到成功的数量）
   today_success = today_total
   # 今日失败 — distinct 账号今日签到失败的
   today_failure = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=0",
        (today,)
    ).fetchone()[0]
   # 累计成功（去重：每个账号只算一次）
   total_success = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE success=1"
   ).fetchone()[0]
   # 累计失败（去重：每个账号只算一次）
   total_failure = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE success=0"
   ).fetchone()[0]

   conn.close()

   # 检测每个账号的签到能力
   accts = []
   for a in accounts:
       d = dict(a)
       cfg = json.loads(d.get("config_json") or "{}")
       d["config"] = cfg
       d["signin_enabled"] = cfg.get("signin_enabled", True)  # 默认启用
       d["signin_time"] = cfg.get("signin_time", "08:00")
       # 检测是否有匹配的签到插件
       from flashsloth.core.signin import get_signin_for_account
       plugin = get_signin_for_account(d)
       d["has_signin"] = plugin is not None
       d["plugin_name"] = plugin.display_name if plugin else ""
       # 找最近签到记录
       last_log = None
       for l in logs:
           if l["account_id"] == d["id"]:
               last_log = dict(l)
               break
       d["last_signin"] = last_log
       accts.append(d)

   # 排序：有签到功能+已启用+未签到 → 有签到功能+已启用+已签到 → 有签到功能+禁用 → 无签到功能
   def sort_key(a):
       has = a["has_signin"]
       enabled = a["signin_enabled"]
       last = a["last_signin"]
       signed_today = 0
       if last and last.get("success") and last.get("created_at", "").startswith(today):
           signed_today = 1
       return (-has, -enabled, -signed_today)

   accts.sort(key=sort_key)

   # 已注册的签到插件列表
   from flashsloth.core.signin import list_signins
   signin_plugins = list_signins()

   return render_template("signin.html",
                        accounts=accts,
                        logs=[dict(l) for l in logs],
                        today_count=today_count,
                        today_total=today_total,
                        today_success=today_success,
                        today_failure=today_failure,
                        total_success=total_success,
                        total_failure=total_failure,
                        today=today,
                        signin_plugins=signin_plugins)

@app.route("/api/signin/account/<int:aid>", methods=["POST"])
@login_required
def api_signin_account(aid):
   """对单个账号执行签到（带超时）"""
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   conn.close()
   if not acct:
       return jsonify({"success": False, "error": "账号不存在"})

   d = dict(acct)
   cfg = json.loads(d.get("config_json") or "{}")
   d["config"] = cfg

   from flashsloth.core.signin import get_signin_for_account
   plugin = get_signin_for_account(d)
   if not plugin:
       return jsonify({"success": False, "error": "该平台无匹配的签到插件"})

   with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
       fut = pool.submit(plugin.signin)
       try:
           result = fut.result(timeout=30)
       except concurrent.futures.TimeoutError:
           result = {"success": False, "already_signed": False,
                     "error": "签到超时（>30秒）", "message": ""}
       except Exception as e:
           result = {"success": False, "already_signed": False,
                     "error": f"签到异常: {e}", "message": ""}

   # 记录日志
   site_url = cfg.get("site_url", "")
   from plugins.forum_signin import log_signin, ensure_signin_log_table
   ensure_signin_log_table()
   log_signin(
       account_id=aid,
       platform=d["platform"],
       account_name=d["account_name"],
       site_url=site_url,
       success=result.get("success", False),
       already_signed=result.get("already_signed", False),
       error=result.get("error", ""),
       message=result.get("message", ""),
   )

   # 刷新账号最后签到时间
   result["account_id"] = aid
   result["last_log"] = {
       "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
       "success": result.get("success", False),
   }
   return jsonify(result)

@app.route("/api/signin/config", methods=["GET", "POST"])
@login_required
def api_signin_config():
   """全局签到配置（签到时间等）"""
   if request.method == "POST":
       data = request.get_json() or {}
       # 保存到 provider_config 或单独的表
       conn = get_db()
       existing = conn.execute(
           "SELECT id FROM provider_config WHERE user_id=? AND provider_type='signin_schedule'",
           (current_user.id,)
       ).fetchone()
       if existing:
           conn.execute(
               "UPDATE provider_config SET config_json=? WHERE id=?",
               (json.dumps(data), existing["id"])
           )
       else:
           conn.execute(
               "INSERT INTO provider_config (user_id, provider_type, config_json) VALUES (?, 'signin_schedule', ?)",
               (current_user.id, json.dumps(data))
           )
       conn.commit()

       # 如果设置了 signin_time，自动同步到所有有签到功能的账号
       synced = 0
       if "signin_time" in data:
           new_time = str(data["signin_time"])
           accounts = conn.execute(
               "SELECT id, config_json FROM platform_accounts WHERE user_id=?",
               (current_user.id,)
           ).fetchall()
           for a in accounts:
               acfg = json.loads(a["config_json"]) if a["config_json"] else {}
               # 只更新有签到功能且显式设置了签到时间的账号
               if "signin_time" in acfg or acfg.get("signin_enabled", True):
                   acfg["signin_time"] = new_time
                   conn.execute(
                       "UPDATE platform_accounts SET config_json=? WHERE id=?",
                       (json.dumps(acfg), a["id"])
                   )
                   synced += 1
           conn.commit()

       conn.close()
       return jsonify({"success": True, "synced_count": synced})

   conn = get_db()
   row = conn.execute(
       "SELECT config_json FROM provider_config WHERE user_id=? AND provider_type='signin_schedule'",
       (current_user.id,)
   ).fetchone()
   conn.close()
   cfg = json.loads(row["config_json"]) if row else {}
   return jsonify({
       "success": True,
       "enabled": cfg.get("enabled", False),
       "signin_time": cfg.get("signin_time", "08:00"),
   })

@app.route("/api/signin/run_all", methods=["POST"])
@login_required
def api_signin_run_all():
   """执行所有已启用的签到（逐账号带超时）"""
   conn = get_db()
   accounts = conn.execute(
       "SELECT * FROM platform_accounts WHERE is_active=1 ORDER BY platform, account_name"
   ).fetchall()
   conn.close()

   results = []
   for a in accounts:
       d = dict(a)
       cfg = json.loads(d.get("config_json") or "{}")
       d["config"] = cfg
       if not cfg.get("signin_enabled", True):
           continue

       from flashsloth.core.signin import get_signin_for_account
       plugin = get_signin_for_account(d)
       if not plugin:
           continue

       with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
           fut = pool.submit(plugin.signin)
           try:
               result = fut.result(timeout=30)
           except concurrent.futures.TimeoutError:
               result = {"success": False, "already_signed": False,
                         "error": "超时", "message": ""}
           except Exception as e:
               result = {"success": False, "already_signed": False,
                         "error": str(e), "message": ""}

       site_url = cfg.get("site_url", "")
       from plugins.forum_signin import log_signin, ensure_signin_log_table
       ensure_signin_log_table()
       log_signin(
           account_id=d["id"],
           platform=d["platform"],
           account_name=d["account_name"],
           site_url=site_url,
           success=result.get("success", False),
           already_signed=result.get("already_signed", False),
           error=result.get("error", ""),
           message=result.get("message", ""),
       )
       results.append({
           "account_id": d["id"],
           "account_name": d["account_name"],
           "success": result.get("success", False),
           "already_signed": result.get("already_signed", False),
           "error": result.get("error", ""),
           "message": result.get("message", ""),
       })

   return jsonify({"success": True, "results": results})


@app.route("/api/signin/stats")
@login_required
def api_signin_stats():
    """签到统计 API（JSON 格式，供前端刷新使用）"""
    conn = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=1 AND already_signed=0",
        (today,)
    ).fetchone()[0]
    today_success = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=1",
        (today,)
    ).fetchone()[0]
    today_failure = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=0",
        (today,)
    ).fetchone()[0]
    total_success = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE success=1"
    ).fetchone()[0]
    total_failure = conn.execute(
        "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE success=0"
    ).fetchone()[0]
    conn.close()
    return jsonify({
        "success": True,
        "today_count": today_count,
        "today_success": today_success,
        "today_failure": today_failure,
        "total_success": total_success,
        "total_failure": total_failure,
    })

