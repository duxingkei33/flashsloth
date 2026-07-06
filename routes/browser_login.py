"""FlashSloth Playwright 浏览器登录路由模块"""
from flashsloth.routes._app import app
from flask import request, jsonify

import json, threading

from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.credential_crypto import encrypt_config

# ═══════════════════════════════════════════════════
# 阿莫论坛 (amobbs) Playwright 登录
# ═══════════════════════════════════════════════════

_amobbs_login_instances: dict[str, "AmobbsPlaywrightLogin"] = {}
_amobbs_lock = threading.Lock()

def _get_amobbs_login(session_id: str = "default") -> "AmobbsPlaywrightLogin":
   """获取/创建 amobbs 登录实例（单例，线程安全）"""
   with _amobbs_lock:
       if session_id not in _amobbs_login_instances:
           from plugins.amobbs_login import AmobbsPlaywrightLogin
           inst = AmobbsPlaywrightLogin()
           _amobbs_login_instances[session_id] = inst
       return _amobbs_login_instances[session_id]

@app.route("/api/amobbs/login/start", methods=["POST"])
@login_required
def amobbs_login_start():
   """启动 Amobbs Playwright 登录"""
   aid = request.json.get("account_id", 0)
   username = request.json.get("username", "")
   password = request.json.get("password", "")

   if not username or not password:
       return jsonify({"success": False, "error": "请输入用户名和密码"})

   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_amobbs_login(sess_id)
       result = inst.login(username, password)

       return jsonify(result)
   except Exception as e:
       return jsonify({"success": False, "error": f"启动登录异常: {e}"})

@app.route("/api/amobbs/login/captcha/click", methods=["POST"])
@login_required
def amobbs_captcha_click():
   """点击验证码复选框并提交"""
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_amobbs_login(sess_id)
       result = inst.click_captcha_and_submit()

       # 如果登录成功，把 cookie 存到数据库
       if result.get("logged_in"):
           aid = request.json.get("account_id", 0)
           if aid:
               cookies = result.get("cookies", "")
               conn = get_db()
               acct = conn.execute(
                   "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
                   (aid, current_user.id)
               ).fetchone()
               if acct:
                   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
                   cfg["cookie"] = cookies
                   encrypt_config(cfg)  # 🔐
                   conn.execute(
                       "UPDATE platform_accounts SET config_json=? WHERE id=?",
                       (json.dumps(cfg), aid)
                   )
                   conn.commit()
               conn.close()

       return jsonify(result)
   except Exception as e:
       return jsonify({"success": False, "error": f"验证码处理异常: {e}"})

@app.route("/api/amobbs/login/screenshot", methods=["GET"])
@login_required
def amobbs_screenshot():
   """获取当前登录页面的截图"""
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_amobbs_login(sess_id)
       b64 = inst.take_screenshot()
       return jsonify({"success": True, "image": b64})
   except Exception as e:
       return jsonify({"success": False, "error": f"截图失败: {e}"})

@app.route("/api/amobbs/login/close", methods=["POST"])
@login_required
def amobbs_login_close():
   """关闭 amobbs 浏览器会话"""
   try:
       sess_id = f"user_{current_user.id}"
       with _amobbs_lock:
           inst = _amobbs_login_instances.pop(sess_id, None)
       if inst:
           inst.close()
       return jsonify({"success": True})
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

# ═══════════════════════════════════════════════════
# 闲鱼 (xianyu) Playwright 登录
# ═══════════════════════════════════════════════════

_xianyu_login_instances: dict[str, "XianyuPlaywrightLogin"] = {}
_xianyu_lock = threading.Lock()

def _get_xianyu_login(session_id: str = "default"):
   with _xianyu_lock:
       if session_id not in _xianyu_login_instances:
           from plugins.xianyu_login import XianyuPlaywrightLogin
           inst = XianyuPlaywrightLogin()
           _xianyu_login_instances[session_id] = inst
       return _xianyu_login_instances[session_id]

@app.route("/api/xianyu/login/start", methods=["POST"])
@login_required
def xianyu_login_start():
   aid = request.json.get("account_id", 0)
   username = request.json.get("username", "")
   password = request.json.get("password", "")
   if not username or not password:
       return jsonify({"success": False, "error": "请输入用户名和密码"})
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_xianyu_login(sess_id)
       result = inst.login(username, password)
       return jsonify(result)
   except Exception as e:
       return jsonify({"success": False, "error": f"启动登录异常: {e}"})

@app.route("/api/xianyu/login/solve", methods=["POST"])
@login_required
def xianyu_login_solve():
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_xianyu_login(sess_id)
       result = inst.solve_and_login()
       if result.get("logged_in"):
           aid = request.json.get("account_id", 0)
           if aid:
               cookies = result.get("cookies", "")
               conn = get_db()
               acct = conn.execute(
                   "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
                   (aid, current_user.id)
               ).fetchone()
               if acct:
                   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
                   cfg["cookie"] = cookies
                   encrypt_config(cfg)  # 🔐
                   conn.execute(
                       "UPDATE platform_accounts SET config_json=? WHERE id=?",
                       (json.dumps(cfg), aid)
                   )
                   conn.commit()
               conn.close()
       return jsonify(result)
   except Exception as e:
       return jsonify({"success": False, "error": f"验证码处理异常: {e}"})

@app.route("/api/xianyu/login/screenshot", methods=["GET"])
@login_required
def xianyu_screenshot():
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_xianyu_login(sess_id)
       return jsonify({"success": True, "image": inst.take_screenshot()})
   except Exception as e:
       return jsonify({"success": False, "error": f"截图失败: {e}"})

@app.route("/api/xianyu/login/close", methods=["POST"])
@login_required
def xianyu_login_close():
   try:
       sess_id = f"user_{current_user.id}"
       with _xianyu_lock:
           inst = _xianyu_login_instances.pop(sess_id, None)
       if inst:
           inst.close()
       return jsonify({"success": True})
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

# ═══════════════════════════════════════════════════
# OSHWHub Playwright 登录
# ═══════════════════════════════════════════════════

_oshwhub_login_instances: dict[str, "OshwhubPlaywrightLogin"] = {}
_oshwhub_lock = threading.Lock()

def _get_oshwhub_login(session_id: str = "default"):
   with _oshwhub_lock:
       if session_id not in _oshwhub_login_instances:
           from plugins.oshwhub_login import OshwhubPlaywrightLogin
           inst = OshwhubPlaywrightLogin()
           _oshwhub_login_instances[session_id] = inst
       return _oshwhub_login_instances[session_id]

@app.route("/api/oshwhub/login/start", methods=["POST"])
@login_required
def oshwhub_login_start():
   aid = request.json.get("account_id", 0)
   username = request.json.get("username", "")
   password = request.json.get("password", "")
   if not username or not password:
       return jsonify({"success": False, "error": "请输入用户名和密码"})
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_oshwhub_login(sess_id)
       result = inst.login(username, password)
       return jsonify(result)
   except Exception as e:
       return jsonify({"success": False, "error": f"启动登录异常: {e}"})

@app.route("/api/oshwhub/login/captcha/click", methods=["POST"])
@login_required
def oshwhub_captcha_click():
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_oshwhub_login(sess_id)
       result = inst.submit_captcha_and_login()
       if result.get("logged_in"):
           aid = request.json.get("account_id", 0)
           if aid:
               cookies = result.get("cookies", "")
               conn = get_db()
               acct = conn.execute(
                   "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
                   (aid, current_user.id)
               ).fetchone()
               if acct:
                   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
                   cfg["cookie"] = cookies
                   encrypt_config(cfg)  # 🔐
                   conn.execute(
                       "UPDATE platform_accounts SET config_json=? WHERE id=?",
                       (json.dumps(cfg), aid)
                   )
                   conn.commit()
               conn.close()
       return jsonify(result)
   except Exception as e:
       return jsonify({"success": False, "error": f"验证码处理异常: {e}"})

@app.route("/api/oshwhub/login/screenshot", methods=["GET"])
@login_required
def oshwhub_screenshot():
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_oshwhub_login(sess_id)
       return jsonify({"success": True, "image": inst.take_screenshot()})
   except Exception as e:
       return jsonify({"success": False, "error": f"截图失败: {e}"})

@app.route("/api/oshwhub/login/close", methods=["POST"])
@login_required
def oshwhub_login_close():
   try:
       sess_id = f"user_{current_user.id}"
       with _oshwhub_lock:
           inst = _oshwhub_login_instances.pop(sess_id, None)
       if inst:
           inst.close()
       return jsonify({"success": True})
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

