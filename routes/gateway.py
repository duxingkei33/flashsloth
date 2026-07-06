"""FlashSloth — 通知网关管理路由"""
from flashsloth.routes._app import app

import json
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
