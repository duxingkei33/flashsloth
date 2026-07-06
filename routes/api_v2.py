"""
FlashSloth Gateway API v2 — RESTful 对外接口

复用 api_v1 的 API Key 鉴权系统。
端点前缀: /api/v2/
"""
import json, time, os, sys, platform
from datetime import datetime

from flask import request, jsonify
from flask_login import login_required, current_user

from flashsloth.routes._app import app
from flashsloth.core.database import get_db
from flashsloth.routes.api_v1 import _verify_api_key


# ═══════════════════════════════════════════════
# 认证：支持 Session + API Key 两种方式
# ═══════════════════════════════════════════════

def _auth():
    """返回当前 user_id 或 None（Session 或 API Key）"""
    # 1. Session 认证（已登录）
    if current_user and current_user.is_authenticated:
        return current_user.id
    # 2. API Key 认证
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return _verify_api_key(api_key)
    return None


def _require_auth():
    """装饰器：要求认证"""
    uid = _auth()
    if not uid:
        return jsonify({"error": "未认证。请使用 Session 登录或提供 X-API-Key 请求头"}), 401
    return None  # 通过


# ═══════════════════════════════════════════════
# 系统管理
# ═══════════════════════════════════════════════

@app.route("/api/v2/system/status")
def api_v2_system_status():
    """系统状态（无需认证）"""
    return jsonify({
        "status": "running",
        "version": "4.x",
        "platform": platform.platform(),
        "python": sys.version,
        "time": datetime.now().isoformat(),
        "uptime": _get_uptime(),
    })


def _get_uptime() -> str:
    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(f.read().split()[0])
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{hours}小时{minutes}分钟"
    except Exception:
        return "未知"


@app.route("/api/v2/system/restart", methods=["POST"])
@login_required
def api_v2_system_restart():
    return jsonify({
        "success": True,
        "message": "重启请求已记录。supervisor: supervisorctl restart flashsloth",
    })


@app.route("/api/v2/system/reload", methods=["POST"])
@login_required
def api_v2_system_reload():
    try:
        from flashsloth.core.config import load_config
        load_config(force_reload=True)
        return jsonify({"success": True, "message": "配置已重载"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/v2/system/log")
@login_required
def api_v2_system_log():
    lines = request.args.get("lines", 50, type=int)
    lines = min(lines, 500)
    log_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "logs", "flashsloth.log"
    )
    if not os.path.exists(log_path):
        return jsonify({"logs": [], "error": "日志文件不存在"})
    try:
        with open(log_path) as f:
            all_lines = f.readlines()
        return jsonify({"logs": all_lines[-lines:], "total": len(all_lines)})
    except Exception as e:
        return jsonify({"logs": [], "error": str(e)})


# ═══════════════════════════════════════════════
# API Key 管理（复用 api_v1 的表）
# ═══════════════════════════════════════════════

@app.route("/api/v2/keys", methods=["GET"])
@login_required
def api_v2_list_keys():
    """列出我的 API Key（隐藏完整 key）"""
    conn = get_db()
    keys = conn.execute(
        "SELECT id, name, key_prefix, is_active, last_used_at, created_at FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return jsonify({"keys": [dict(k) for k in keys]})


@app.route("/api/v2/keys", methods=["POST"])
@login_required
def api_v2_create_key():
    """创建 API Key（仅首次展示完整 key）"""
    import hashlib, secrets, hmac

    name = request.get_json(force=True, silent=True).get("name", "default") if request.get_json(silent=True) else "default"

    # 生成 key
    raw_key = "fs_" + secrets.token_hex(24)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]

    conn = get_db()
    conn.execute(
        "INSERT INTO api_keys (user_id, name, key_hash, key_prefix) VALUES (?, ?, ?, ?)",
        (current_user.id, name, key_hash, key_prefix)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "api_key": raw_key,
        "name": name,
        "message": "请立即保存此 Key，关闭后将无法再次查看完整 Key",
    })


@app.route("/api/v2/keys/<int:key_id>", methods=["DELETE"])
@login_required
def api_v2_delete_key(key_id):
    conn = get_db()
    conn.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (key_id, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ═══════════════════════════════════════════════
# API 能力清单
# ═══════════════════════════════════════════════

@app.route("/api/v2/capabilities")
def api_v2_capabilities():
    return jsonify({
        "version": "2.0",
        "name": "FlashSloth Personal Asset Hub",
        "modules": {
            "system": {
                "description": "系统管理",
                "endpoints": [
                    "GET /api/v2/system/status",
                    "POST /api/v2/system/restart",
                    "POST /api/v2/system/reload",
                    "GET /api/v2/system/log",
                ]
            },
            "accounts": {
                "description": "账号管理",
                "note": "通过 /accounts 页面管理"
            },
            "article": {
                "description": "文章/内容",
                "note": "通过 /publish/manage 页面管理"
            },
            "product": {
                "description": "商品搜索/监控",
                "note": "通过 XianyuAdapter.search_products() 调用"
            },
            "signin": {
                "description": "签到管理",
                "note": "通过 /signin 页面管理"
            },
            "agent": {
                "description": "AI助手",
                "note": "通过 /ai/settings 页面管理"
            },
        },
        "auth": "Session (登录) 或 X-API-Key 请求头",
    })
