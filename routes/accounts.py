"""FlashSloth — 账号管理路由
从 admin.py 提取，使用 Blueprint 重构"""
from flashsloth.routes._app import app


import json

from flask import ( render_template, request, redirect, url_for,
                  flash, jsonify)
from flask_login import login_required, current_user

from flashsloth.core.database import get_db, DB_PATH
from flashsloth.core.publisher import get_publisher, list_publishers

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
   """返回指定账号的配置（含密码脱敏）"""
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   conn.close()
   if not acct:
       return jsonify({"success": False, "error": "账号不存在"})
   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   return jsonify({"success": True, "config": cfg})

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
   conn = get_db()
   conn.execute(
       "INSERT INTO platform_accounts (user_id, platform, account_name, config_json) VALUES (?, ?, ?, ?)",
       (current_user.id, platform, name, json.dumps(cfg)),
   )
   conn.commit()
   conn.close()
   flash(f"{platform} 账号已添加", "success")
   return redirect(url_for("accounts"))

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
   if request.method == "POST":
       name = request.form.get("account_name", "")
       cfg = {}
       for key in request.form:
           if key.startswith("cfg_"):
               cfg[key[4:]] = request.form[key]
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
   platforms = list_publishers()
   return render_template("account_edit.html",
                        account=dict(acct),
                        platforms=platforms)

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
   """检查账号登录状态（含 cookie 有效性检测）"""
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
   cookie = cfg.get("cookie", "")
   site_url = cfg.get("site_url", "")
   result = {
       "success": True,
       "platform": acct["platform"],
       "account_name": acct["account_name"],
       "is_active": bool(acct["is_active"]),
       "has_cookie": bool(cookie),
       "site_url": site_url or "",
   }
   if cookie and site_url:
       try:
           import requests
           r = requests.get(
               site_url.rstrip("/") + "/forum.php",
               headers={
                   "Cookie": cookie,
                   "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
               },
               timeout=15
           )
           result["status_code"] = r.status_code
           html_lower = r.text.lower()
           # 登录检测关键词
           login_keywords = ["欢迎", "退出", "logout", "我的帖子", "我的中心",
                             "个人中心", "设置", "消息", "提醒"]
           logout_keywords = ["登录", "注册", "立即登录", "找回密码"]
           is_logged_in = False
           for kw in login_keywords:
               if kw in r.text:
                   is_logged_in = True
                   break
           if not is_logged_in:
               for kw in logout_keywords:
                   if kw in html_lower and "登录" in r.text:
                       is_logged_in = False
                       break
           result["logged_in"] = is_logged_in
           result["status"] = "✅ 已登录（Cookie 有效）" if is_logged_in else "❌ Cookie 已失效"
           import re
           tm = re.search(r'<title>(.*?)</title>', r.text)
           result["page_title"] = tm.group(1) if tm else "(无标题)"
           text = re.sub(r'<script[^>]*>.*?</script>', '', r.text, flags=re.DOTALL)
           text = re.sub(r'<[^>]+>', ' ', text)
           text = re.sub(r'\s+', ' ', text).strip()
           result["page_preview"] = text[:600]
       except Exception as e:
           result["logged_in"] = False
           result["status"] = f"❌ 检测异常: {str(e)[:100]}"
   elif cookie:
       result["logged_in"] = None
       result["status"] = "🍪 有 Cookie（未配置站点 URL，无法检测有效性）"
   else:
       result["logged_in"] = None
       result["status"] = "⏸️ 未配置（无 Cookie）"
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

