"""FlashSloth Playwright 浏览器登录路由模块"""
import json, threading, logging
from flashsloth.routes._app import app
from flask import request, jsonify

from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.credential_crypto import encrypt_config
from flashsloth.routes.accounts.helpers import _get_engine_for_platform

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# 通用登录分发辅助函数（数据驱动 — 从 engine 字段判断）
# ═══════════════════════════════════════════════════

def _dispatch_platform_login(platform: str, action: str, data: dict, aid: int) -> dict:
    """根据平台引擎类型分发登录操作（start / captcha / screenshot / submit_captcha / close）

    数据驱动（铁律#19）：通过 _get_engine_for_platform 从探索数据 engine 字段判断。
    """
    engine = _get_engine_for_platform(platform)
    sess_id = f"user_{current_user.id}"

    if engine == "discuz":
        site_url = data.get("site_url", "")
        inst = _get_discuz_login(sess_id, site_url=site_url, platform=platform)
        if action == "start":
            username = data.get("username", "")
            password = data.get("password", "")
            return inst.login(username, password)
        elif action == "captcha":
            return inst.click_captcha_and_submit()
        elif action == "screenshot":
            return {"success": True, "image": inst.take_screenshot()}
        elif action == "close":
            _close_discuz_login(sess_id)
            return {"success": True}
        return {"success": False, "error": f"不支持的操作: {action}"}

    elif engine == "xianyu":
        inst = _get_xianyu_login(sess_id)
        if action == "start":
            username = data.get("username", "")
            password = data.get("password", "")
            return inst.login(username, password)
        elif action == "captcha":
            return inst.solve_and_login()
        elif action == "screenshot":
            return {"success": True, "image": inst.take_screenshot()}
        elif action == "close":
            with _xianyu_lock:
                inst = _xianyu_login_instances.pop(sess_id, None)
            if inst:
                inst.close()
            return {"success": True}
        return {"success": False, "error": f"不支持的操作: {action}"}

    elif engine == "oshwhub":
        inst = _get_oshwhub_login(sess_id)
        if action == "start":
            username = data.get("username", "")
            password = data.get("password", "")
            return inst.login(username, password)
        elif action == "captcha":
            return inst.submit_captcha_and_login()
        elif action == "screenshot":
            return {"success": True, "image": inst.take_screenshot()}
        elif action == "close":
            with _oshwhub_lock:
                inst = _oshwhub_login_instances.pop(sess_id, None)
            if inst:
                inst.close()
            return {"success": True}
        return {"success": False, "error": f"不支持的操作: {action}"}

    return {"success": False, "error": f"平台 {platform} 引擎 {engine} 不支持浏览器登录"}


# ═══════════════════════════════════════════════════
# 通用 Discuz 系论坛 Playwright 登录（支持 amobbs/mydigit/discuz 等）
# ═══════════════════════════════════════════════════

_discuz_login_instances: dict[str, "AmobbsPlaywrightLogin"] = {}
_discuz_lock = threading.Lock()

def _get_discuz_login(session_id: str, site_url: str = "", platform: str = "") -> "AmobbsPlaywrightLogin":
    """获取/创建 Discuz 系论坛登录实例（按 session_id 区分）

    数据驱动（铁律#19）：如果 site_url 为空，尝试从账号配置读取。
    site_url 变化时自动重建实例。
    platform 参数：指定平台名（如 mydigit/discuz/amobbs），用于数据驱动读取 site_url
    """
    with _discuz_lock:
        if not site_url:
            # site_url 为空时，尝试从当前账号配置读取
            from flask_login import current_user
            from flashsloth.core.database import get_db
            try:
                uid = current_user.id
                conn = get_db()
                row = conn.execute(
                    "SELECT config_json FROM platform_accounts WHERE user_id=? AND platform='discuz' LIMIT 1",
                    (uid,)
                ).fetchone()
                if row:
                    import json as _json
                    cfg = _json.loads(row["config_json"])
                    site_url = cfg.get("site_url", "")
                conn.close()
            except Exception:
                site_url = ""
        
        # site_url 变化时重建实例
        if session_id in _discuz_login_instances:
            existing = _discuz_login_instances[session_id]
            if existing.site_url.rstrip("/") == site_url.rstrip("/"):
                return existing
            # site_url 变了 → 关闭旧实例重建
            try:
                existing.close()
            except Exception:
                pass
            del _discuz_login_instances[session_id]
        
        from plugins.amobbs_login import AmobbsPlaywrightLogin
        inst = AmobbsPlaywrightLogin(site_url=site_url, platform=platform)
        _discuz_login_instances[session_id] = inst
        return inst

def _close_discuz_login(session_id: str):
    """关闭 Discuz 登录实例"""
    with _discuz_lock:
        inst = _discuz_login_instances.pop(session_id, None)
    if inst:
        inst.close()

# ═══════════════════════════════════════════════════
# 阿莫论坛 (amobbs) Playwright 登录（向下兼容）
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
   """[DEPRECATED] 启动 Amobbs Playwright 登录，请使用 /api/platform/amobbs/login/start"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: amobbs/login/start")
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
   """[DEPRECATED] 点击验证码复选框并提交，请使用 /api/platform/amobbs/login/captcha"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: amobbs/login/captcha/click")
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
   """[DEPRECATED] 获取当前登录页面的截图，请使用 /api/platform/amobbs/login/screenshot"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: amobbs/login/screenshot")
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
   """[DEPRECATED] 关闭 amobbs 浏览器会话，请使用 /api/platform/amobbs/login/close"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: amobbs/login/close")
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
   """[DEPRECATED] 启动闲鱼 Playwright 登录，请使用 /api/platform/xianyu/login/start"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: xianyu/login/start")
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
   """[DEPRECATED] 闲鱼验证码处理和登录，请使用 /api/platform/xianyu/login/captcha"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: xianyu/login/solve")
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
   """[DEPRECATED] 获取闲鱼登录截图，请使用 /api/platform/xianyu/login/screenshot"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: xianyu/login/screenshot")
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_xianyu_login(sess_id)
       return jsonify({"success": True, "image": inst.take_screenshot()})
   except Exception as e:
       return jsonify({"success": False, "error": f"截图失败: {e}"})

@app.route("/api/xianyu/login/close", methods=["POST"])
@login_required
def xianyu_login_close():
   """[DEPRECATED] 关闭闲鱼浏览器会话，请使用 /api/platform/xianyu/login/close"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: xianyu/login/close")
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
   """[DEPRECATED] 启动 OSHWHub Playwright 登录，请使用 /api/platform/oshwhub/login/start"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: oshwhub/login/start")
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
   """[DEPRECATED] 提交 OSHWHub 验证码并登录，请使用 /api/platform/oshwhub/login/captcha"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: oshwhub/login/captcha/click")
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
   """[DEPRECATED] 获取 OSHWHub 登录截图，请使用 /api/platform/oshwhub/login/screenshot"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: oshwhub/login/screenshot")
   try:
       sess_id = f"user_{current_user.id}"
       inst = _get_oshwhub_login(sess_id)
       return jsonify({"success": True, "image": inst.take_screenshot()})
   except Exception as e:
       return jsonify({"success": False, "error": f"截图失败: {e}"})

@app.route("/api/oshwhub/login/close", methods=["POST"])
@login_required
def oshwhub_login_close():
   """[DEPRECATED] 关闭 OSHWHub 浏览器会话，请使用 /api/platform/oshwhub/login/close"""
   logger.warning("[DEPRECATED] 使用旧版登录路由: oshwhub/login/close")
   try:
       sess_id = f"user_{current_user.id}"
       with _oshwhub_lock:
           inst = _oshwhub_login_instances.pop(sess_id, None)
       if inst:
           inst.close()
       return jsonify({"success": True})
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

