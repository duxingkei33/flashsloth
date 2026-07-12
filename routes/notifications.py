"""FlashSloth — 通知系统路由"""
from flashsloth.routes._app import app

from flask import (render_template, jsonify, request, redirect, url_for)
from flask_login import login_required, current_user

from flashsloth.core.notifier import (
    get_notifications, mark_read, mark_all_read, get_unread_count,
)


@app.route("/notifications")
@login_required
def notifications_page():
    """通知中心页面"""
    return render_template("notifications.html")


@app.route("/api/notifications")
@login_required
def api_notifications():
    """获取通知列表"""
    unread_only = request.args.get("unread_only", "").lower() in ("1", "true")
    level = request.args.get("level", "")
    source = request.args.get("source", "")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    items = get_notifications(
        user_id=current_user.id,
        unread_only=unread_only,
        level=level or None,
        source=source or None,
        limit=limit,
        offset=offset,
    )
    unread_count = get_unread_count(current_user.id)

    return jsonify({
        "notifications": items,
        "unread_count": unread_count,
        "total": len(items),
    })


@app.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required
def api_notification_read(nid):
    """标记通知已读"""
    result = mark_read(nid)
    return jsonify(result)


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def api_notifications_read_all():
    """全部已读"""
    result = mark_all_read(current_user.id)
    return jsonify(result)


@app.route("/api/notifications/unread-count")
@login_required
def api_notifications_unread_count():
    """未读数（供navbar轮询）"""
    count = get_unread_count(current_user.id)
    return jsonify({"count": count})
