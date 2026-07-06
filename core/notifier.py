"""FlashSloth — 统一通知系统

用途：提供给所有模块(文章/视频/购物/流水线/签到等)统一的推送通道。
支持渠道：Web站内信 + 网关多终端广播（飞书/企微/Webhook等）

用法：
    from flashsloth.core.notifier import notify, notify_info, notify_warn, notify_error

    notify_info("文章发布成功", "《xxx》已发布到 WordPress")
    notify_error("闲鱼搜索失败", "Cookie 已过期，请重新登录")

当网关有已启用的终端时，notify() 会自动通过网关广播到所有终端。
"""
from typing import Optional
from datetime import datetime
from flashsloth.core.database import get_db


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _broadcast_to_gateway(title, message, level, source, link):
    """自动广播到网关终端（静默，不阻塞主流程）"""
    try:
        from flashsloth.core.gateway import get_gateway, GatewayMessage
        gw = get_gateway()
        channels = gw._load_channels()
        if channels:
            msg = GatewayMessage(
                title=title, body=message, level=level,
                source=source, link=link,
                timestamp=_now(),
            )
            gw.dispatch(msg)
    except Exception:
        pass  # 网关不可用时静默跳过，不影响主流程


def notify(
    title: str,
    message: str = "",
    level: str = "info",
    source: str = "system",
    user_id: int = 1,
    link: str = "",
) -> dict:
    """发送通知

    参数:
        title: 通知标题
        message: 通知正文
        level: info | success | warn | error
        source: 来源模块标识
        user_id: 接收用户ID
        link: 点击跳转链接
    返回:
        {"success": True, "id": N}
    """
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO notifications (user_id, title, message, level, source, link, is_read, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (user_id, title, message, level, source, link, _now()),
        )
        conn.commit()
        notification_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        # 自动广播到网关终端
        _broadcast_to_gateway(title, message, level, source, link)
        return {"success": True, "id": notification_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


def notify_info(title: str, message: str = "", source: str = "system", link: str = "") -> dict:
    return notify(title, message, "info", source, link=link)


def notify_success(title: str, message: str = "", source: str = "system", link: str = "") -> dict:
    return notify(title, message, "success", source, link=link)


def notify_warn(title: str, message: str = "", source: str = "system", link: str = "") -> dict:
    return notify(title, message, "warn", source, link=link)


def notify_error(title: str, message: str = "", source: str = "system", link: str = "") -> dict:
    return notify(title, message, "error", source, link=link)


def get_notifications(
    user_id: int = 1,
    unread_only: bool = False,
    level: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list:
    """获取通知列表"""
    conn = get_db()
    sql = "SELECT * FROM notifications WHERE user_id=?"
    params = [user_id]

    if unread_only:
        sql += " AND is_read=0"
    if level:
        sql += " AND level=?"
        params.append(level)
    if source:
        sql += " AND source=?"
        params.append(source)

    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_read(notification_id: int) -> dict:
    """标记单条已读"""
    try:
        conn = get_db()
        conn.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def mark_all_read(user_id: int = 1) -> dict:
    """标记所有已读"""
    try:
        conn = get_db()
        conn.execute(
            "UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0",
            (user_id,),
        )
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_unread_count(user_id: int = 1) -> int:
    """未读通知数"""
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user_id,),
        ).fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0
