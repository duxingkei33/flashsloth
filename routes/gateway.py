"""FlashSloth — 通知网关管理路由"""
from flashsloth.routes._app import app

import json
import uuid
import threading
from flask import render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

from flashsloth.core.database import get_db
from flashsloth.core.gateway import (
    get_gateway, get_provider, list_providers, GatewayMessage,
)


@app.route("/gateway")
@login_required
def gateway_page():
    """通知网关配置页面"""
    conn = get_db()
    channels = conn.execute(
        "SELECT * FROM gateway_channels WHERE user_id=? ORDER BY platform, created_at",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return render_template("gateway.html",
                         channels=[dict(c) for c in channels],
                         providers=list_providers())


# ─── CRUD: 添加渠道 ────────────────────
@app.route("/api/gateway/channels", methods=["POST"])
@login_required
def api_gateway_add_channel():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    platform = (data.get("platform") or "").strip()
    config = data.get("config", {})

    if not name or not platform:
        return jsonify({"success": False, "error": "名称和平台不能为空"})

    # 验证 Provider 是否存在
    provider = get_provider(platform)
    if not provider:
        return jsonify({"success": False, "error": f"不支持的平台: {platform}"})

    # 验证配置
    valid, msg = provider.validate_config(config)
    if not valid:
        return jsonify({"success": False, "error": msg})

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO gateway_channels (name, platform, config_json, user_id) VALUES (?, ?, ?, ?)",
            (name, platform, json.dumps(config, ensure_ascii=False), current_user.id)
        )
        conn.commit()
        ch_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return jsonify({"success": True, "id": ch_id, "message": f"渠道 '{name}' 已添加"})
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "error": str(e)})


# ─── CRUD: 更新渠道 ────────────────────
@app.route("/api/gateway/channels/<int:ch_id>", methods=["PUT"])
@login_required
def api_gateway_update_channel(ch_id):
    data = request.get_json(force=True, silent=True) or {}
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM gateway_channels WHERE id=? AND user_id=?",
        (ch_id, current_user.id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "渠道不存在"})

    updates = []
    values = []
    for field in ["name", "platform"]:
        if field in data:
            updates.append(f"{field}=?")
            values.append(data[field])
    if "config" in data:
        updates.append("config_json=?")
        values.append(json.dumps(data["config"], ensure_ascii=False))
    if "enabled" in data:
        updates.append("enabled=?")
        values.append(1 if data["enabled"] else 0)
    if "config_json" in data:
        pass  # handled above

    if updates:
        updates.append("updated_at=datetime('now')")
        values.append(ch_id)
        conn.execute(f"UPDATE gateway_channels SET {', '.join(updates)} WHERE id=?", values)
        conn.commit()
    conn.close()

    # 清除网关缓存
    from flashsloth.core.gateway import get_gateway
    get_gateway()._channel_cache = None

    return jsonify({"success": True, "message": "渠道已更新"})


# ─── CRUD: 删除渠道 ────────────────────
@app.route("/api/gateway/channels/<int:ch_id>", methods=["DELETE"])
@login_required
def api_gateway_delete_channel(ch_id):
    conn = get_db()
    conn.execute("DELETE FROM gateway_channels WHERE id=? AND user_id=?", (ch_id, current_user.id))
    conn.commit()
    conn.close()

    from flashsloth.core.gateway import get_gateway
    get_gateway()._channel_cache = None

    return jsonify({"success": True, "message": "渠道已删除"})


# ─── 测试渠道 ─────────────────────────
@app.route("/api/gateway/channels/<int:ch_id>/test", methods=["POST"])
@login_required
def api_gateway_test_channel(ch_id):
    from flashsloth.core.gateway import get_gateway
    result = get_gateway().test_channel(ch_id)
    return jsonify(result)


# ─── 发送测试消息到所有渠道 ────────────
@app.route("/api/gateway/test-all", methods=["POST"])
@login_required
def api_gateway_test_all():
    msg = GatewayMessage(
        title="🔔 FlashSloth 网关全域测试",
        body="如果您收到此消息，说明通知网关工作正常。\n\n发送时间: " + __import__('datetime').datetime.now().isoformat(),
        level="info",
        source="gateway",
    )
    from flashsloth.core.gateway import get_gateway
    results = get_gateway().dispatch(msg)
    success_count = sum(1 for r in results if r.get("success"))
    return jsonify({
        "success": success_count > 0,
        "total": len(results),
        "success_count": success_count,
        "results": results,
    })


# ─── 获取 Provider 列表 ────────────────
@app.route("/api/gateway/providers")
@login_required
def api_gateway_providers():
    providers = []
    for p in list_providers():
        providers.append({
            "name": p.name,
            "display_name": p.display_name,
            "icon": p.icon,
            "description": p.description,
            "config_fields": p.config_fields,
        })
    return jsonify({"providers": providers})


# ─── 获取渠道列表 ─────────────────────
@app.route("/api/gateway/channels")
@login_required
def api_gateway_channels():
    conn = get_db()
    channels = conn.execute(
        "SELECT * FROM gateway_channels WHERE user_id=? ORDER BY platform, created_at",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return jsonify({"channels": [dict(c) for c in channels]})


# ─── QR 扫码自动配置 ─────────────────────
# 临时会话存储（内存，重启后清空）
_qr_sessions: dict = {}
_qr_lock = threading.Lock()


@app.route("/api/gateway/start-callback", methods=["POST"])
@login_required
def api_gateway_start_callback():
    """启动扫码自动配置流程：生成回调地址 + 会话"""
    data = request.get_json(force=True, silent=True) or {}
    platform = (data.get("platform") or "").strip()
    if not platform:
        return jsonify({"success": False, "error": "platform 必填"})

    # 生成唯一会话 ID
    session_id = uuid.uuid4().hex[:12]
    tunnel_url = "http://103.97.178.234:5001"

    # 回调地址：被扫码后平台 POST webhook 信息到此
    callback_url = f"{tunnel_url}/api/gateway/callback/{session_id}"

    with _qr_lock:
        _qr_sessions[session_id] = {
            "platform": platform,
            "user_id": current_user.id,
            "webhook_url": None,
            "secret": None,
            "created_at": __import__("time").time(),
            "status": "waiting",
        }

    return jsonify({
        "success": True,
        "session_id": session_id,
        "qr_url": callback_url,
    })


@app.route("/api/gateway/callback-result/<session_id>")
@login_required
def api_gateway_callback_result(session_id):
    """轮询回调结果"""
    with _qr_lock:
        sess = _qr_sessions.get(session_id)
    if not sess:
        return jsonify({"success": False, "error": "会话不存在或已过期"})
    if sess["user_id"] != current_user.id:
        return jsonify({"success": False, "error": "无权限"})

    if sess["webhook_url"]:
        return jsonify({
            "success": True,
            "webhook_url": sess["webhook_url"],
            "secret": sess.get("secret"),
        })
    # 5 分钟超时
    if __import__("time").time() - sess["created_at"] > 300:
        with _qr_lock:
            _qr_sessions.pop(session_id, None)
        return jsonify({"success": False, "error": "超时"})
    return jsonify({"success": False, "error": "等待中"})


@app.route("/api/gateway/callback/<session_id>", methods=["POST"])
def api_gateway_webhook_callback(session_id):
    """外部平台回调端点 — 接收扫码后发送的 webhook 验证请求"""
    with _qr_lock:
        sess = _qr_sessions.get(session_id)
    if not sess:
        return jsonify({"error": "会话不存在"}), 404

    data = request.get_json(force=True, silent=True) or {}
    # 不同平台不同字段名，统一提取
    webhook_url = (
        data.get("webhook_url") or data.get("url") or
        data.get("request_url") or data.get("callback_url") or ""
    )
    secret = data.get("secret") or data.get("token") or ""

    with _qr_lock:
        sess["webhook_url"] = webhook_url
        sess["secret"] = secret
        sess["status"] = "completed"

    return jsonify({"success": True})
