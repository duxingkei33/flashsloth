"""FlashSloth — 审批流程管理路由"""
from flashsloth.routes._app import app

import json
from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from flashsloth.core.approval import (
    init_approval_table, create_approval, process_approval,
    get_pending_approvals, get_approval_history, get_approval, cancel_approval,
)


# 初始化审批表
init_approval_table()


@app.route("/approval")
@login_required
def approval_page():
    """审批管理页面"""
    pending = get_pending_approvals()
    history = get_approval_history(limit=50)
    return render_template("approval.html",
                         pending=[p.to_dict() for p in pending],
                         history=[h.to_dict() for h in history])


# ─── API: 获取待审批列表 ─────────────────
@app.route("/api/approval/pending")
@login_required
def api_approval_pending():
    pending = get_pending_approvals()
    return jsonify({"success": True, "pending": [p.to_dict() for p in pending],
                    "count": len(pending)})


# ─── API: 获取审批历史 ─────────────────
@app.route("/api/approval/history")
@login_required
def api_approval_history():
    history = get_approval_history()
    return jsonify({"success": True, "history": [h.to_dict() for h in history],
                    "count": len(history)})


# ─── API: 通过/拒绝审批 ─────────────────
@app.route("/api/approval/<int:approval_id>/respond", methods=["POST"])
@login_required
def api_approval_respond(approval_id):
    data = request.get_json() or {}
    approved = data.get("approved", False)
    note = data.get("note", "")
    
    req = process_approval(approval_id, approved, note)
    if not req:
        return jsonify({"success": False, "error": "审批请求不存在"})
    
    return jsonify({
        "success": True,
        "message": f"审批已{'通过' if approved else '拒绝'}",
        "approval": req.to_dict(),
    })


# ─── API: 取消审批 ─────────────────────
@app.route("/api/approval/<int:approval_id>/cancel", methods=["POST"])
@login_required
def api_approval_cancel(approval_id):
    if cancel_approval(approval_id):
        return jsonify({"success": True, "message": "审批已取消"})
    return jsonify({"success": False, "error": "审批不存在或已被处理"})


# ─── API: 创建审批（供其他模块调用） ─────
@app.route("/api/approval/create", methods=["POST"])
@login_required
def api_approval_create():
    data = request.get_json() or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"success": False, "error": "审批标题不能为空"})
    
    try:
        req = create_approval(
            title=title,
            description=data.get("description", ""),
            action=data.get("action", "custom"),
            target_platform=data.get("target_platform", ""),
            target_url=data.get("target_url", ""),
            metadata=data.get("metadata", {}),
            notify=data.get("notify", True),
        )
        return jsonify({"success": True, "message": "审批请求已创建并通知",
                        "approval": req.to_dict()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ─── Webhook: 接收来自网关的审批回复 ─────
@app.route("/api/approval/webhook", methods=["POST"])
def api_approval_webhook():
    """接收外部系统（如iLink Bot回调）的审批回复
    
    支持的格式:
    - 文本回复: "通过 123" 或 "拒绝 123"
    - 结构化JSON: {"approval_id": 123, "approved": true, "note": "OK"}
    """
    data = request.get_json(silent=True) or {}
    
    # 结构化JSON
    if "approval_id" in data:
        req = process_approval(
            data["approval_id"],
            data.get("approved", False),
            data.get("note", ""),
        )
        if req:
            status_text = "通过" if data.get("approved") else "拒绝"
            return jsonify({"success": True, "message": f"审批#{req.id}已{status_text}"})
        return jsonify({"success": False, "error": "审批不存在"})
    
    # 文本回复: 解析 "通过 123" / "拒绝 123" 格式
    content = data.get("content", "") or data.get("text", "") or data.get("message", "")
    if not content:
        return jsonify({"success": False, "error": "无法解析审批回复"})
    
    content = content.strip()
    import re
    m = re.match(r"(通过|批准|同意|ok|yes|approve)\s*[:：]?\s*(\d+)", content, re.IGNORECASE)
    if m:
        req = process_approval(int(m.group(2)), True, content)
        if req:
            return jsonify({"success": True, "message": f"审批#{req.id}已通过"})
        return jsonify({"success": False, "error": f"审批#{m.group(2)}不存在"})
    
    m = re.match(r"(拒绝|驳回|不同意|no|reject)\s*[:：]?\s*(\d+)", content, re.IGNORECASE)
    if m:
        req = process_approval(int(m.group(2)), False, content)
        if req:
            return jsonify({"success": True, "message": f"审批#{req.id}已拒绝"})
        return jsonify({"success": False, "error": f"审批#{m.group(2)}不存在"})
    
    return jsonify({"success": False, "error": "无法解析审批回复，格式:「通过 123」或「拒绝 123」"})
