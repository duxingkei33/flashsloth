"""FlashSloth — 统一日志管理 API（发布日志 / 签到日志 / 部署日志 / AI 日志）
AI 日志复用 routes/ai.py 已有接口，其他三表直接操作数据库。"""
from flashsloth.routes._app import app

import json

from flask import render_template, request, jsonify, redirect
from flask_login import login_required, current_user

from flashsloth.core.database import get_db


# ═══════════════════════════════════════════════════════════
# 统一日志管理页面
# ═══════════════════════════════════════════════════════════

@app.route("/logs")
@login_required
def logs_page():
    """统一日志管理页面"""
    return render_template("logs.html")


# ═══════════════════════════════════════════════════════════
# 统计 API
# ═══════════════════════════════════════════════════════════

@app.route("/api/logs/stats")
@login_required
def api_logs_stats():
    """返回各日志表的记录数统计"""
    conn = get_db()
    stats = {
        "publish": conn.execute("SELECT COUNT(*) FROM publish_log").fetchone()[0],
        "signin": conn.execute("SELECT COUNT(*) FROM signin_log").fetchone()[0],
        "ai": conn.execute("SELECT COUNT(*) FROM ai_call_log").fetchone()[0],
        "deploy": conn.execute("SELECT COUNT(*) FROM deploy_log").fetchone()[0],
    }
    conn.close()
    return jsonify({"success": True, "stats": stats})


# ═══════════════════════════════════════════════════════════
# 发布日志 (publish_log)
# ═══════════════════════════════════════════════════════════

@app.route("/api/logs/publish")
@login_required
def api_logs_publish_list():
    """发布日志列表（分页，JOIN platform_accounts 取 account_name）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM publish_log").fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        """SELECT p.*, COALESCE(a.account_name, '') AS account_name
           FROM publish_log p
           LEFT JOIN platform_accounts a ON p.account_id = a.id
           ORDER BY p.created_at DESC
           LIMIT ? OFFSET ?""",
        (per_page, offset),
    ).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "total": total,
        "page": page,
        "per_page": per_page,
        "logs": [dict(r) for r in rows],
    })


@app.route("/api/logs/publish/<int:log_id>", methods=["DELETE"])
@login_required
def api_logs_publish_delete(log_id):
    """删除单条发布日志"""
    conn = get_db()
    row = conn.execute("SELECT id FROM publish_log WHERE id=?", (log_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "日志不存在"}), 404
    conn.execute("DELETE FROM publish_log WHERE id=?", (log_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "日志已删除"})


@app.route("/api/logs/publish/clear", methods=["POST"])
@login_required
def api_logs_publish_clear():
    """清空发布日志（需要管理员权限）"""
    if not getattr(current_user, "is_admin", 0):
        return jsonify({"success": False, "error": "需要管理员权限"}), 403
    conn = get_db()
    conn.execute("DELETE FROM publish_log")
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "发布日志已清空"})


# ═══════════════════════════════════════════════════════════
# 签到日志 (signin_log)
# ═══════════════════════════════════════════════════════════

@app.route("/api/logs/signin")
@login_required
def api_logs_signin_list():
    """签到日志列表（分页）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM signin_log").fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        "SELECT * FROM signin_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "total": total,
        "page": page,
        "per_page": per_page,
        "logs": [dict(r) for r in rows],
    })


@app.route("/api/logs/signin/<int:log_id>", methods=["DELETE"])
@login_required
def api_logs_signin_delete(log_id):
    """删除单条签到日志"""
    conn = get_db()
    row = conn.execute("SELECT id FROM signin_log WHERE id=?", (log_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "日志不存在"}), 404
    conn.execute("DELETE FROM signin_log WHERE id=?", (log_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "日志已删除"})


@app.route("/api/logs/signin/clear", methods=["POST"])
@login_required
def api_logs_signin_clear():
    """清空签到日志"""
    conn = get_db()
    conn.execute("DELETE FROM signin_log")
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "签到日志已清空"})


# ═══════════════════════════════════════════════════════════
# 部署日志 (deploy_log)
# ═══════════════════════════════════════════════════════════

@app.route("/api/logs/deploy")
@login_required
def api_logs_deploy_list():
    """部署日志列表（分页）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM deploy_log").fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        "SELECT * FROM deploy_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "total": total,
        "page": page,
        "per_page": per_page,
        "logs": [dict(r) for r in rows],
    })


@app.route("/api/logs/deploy/<int:log_id>", methods=["DELETE"])
@login_required
def api_logs_deploy_delete(log_id):
    """删除单条部署日志"""
    conn = get_db()
    row = conn.execute("SELECT id FROM deploy_log WHERE id=?", (log_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "日志不存在"}), 404
    conn.execute("DELETE FROM deploy_log WHERE id=?", (log_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "日志已删除"})


@app.route("/api/logs/deploy/clear", methods=["POST"])
@login_required
def api_logs_deploy_clear():
    """清空部署日志"""
    conn = get_db()
    conn.execute("DELETE FROM deploy_log")
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "部署日志已清空"})


# ═══════════════════════════════════════════════════════════
# AI 日志 (ai_call_log) — 代理到现有 API 或直接操作
# ═══════════════════════════════════════════════════════════

@app.route("/api/logs/ai")
@login_required
def api_logs_ai_list():
    """AI 调用日志列表 — 转发到 /api/ai/logs（保持现有接口）"""
    # 拼接查询参数后重定向
    qs = request.query_string.decode("utf-8") if request.query_string else ""
    url = "/api/ai/logs"
    if qs:
        url += "?" + qs
    return redirect(url)


@app.route("/api/logs/ai/clear", methods=["POST"])
@login_required
def api_logs_ai_clear():
    """清空 AI 调用日志 — 转发到 /api/ai/logs/clear"""
    return redirect("/api/ai/logs/clear", code=307)


@app.route("/api/logs/ai/<int:log_id>", methods=["DELETE"])
@login_required
def api_logs_ai_delete(log_id):
    """删除单条 AI 调用日志（直接操作 ai_call_log 表）"""
    conn = get_db()
    row = conn.execute("SELECT id FROM ai_call_log WHERE id=?", (log_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "日志不存在"}), 404
    conn.execute("DELETE FROM ai_call_log WHERE id=?", (log_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "AI 日志已删除"})
