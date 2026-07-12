"""FlashSloth — 审批流程系统

用途：当AI需要执行敏感操作（如发布内容、删除帖子等）时，
先创建审批请求，通过通知网关（微信/企微/飞书等）发送给管理员，
管理员回复"通过"/"拒绝"来决定是否执行。

流程：
1. create_approval() → 创建待审批记录 + 发通知
2. 管理员通过网关回复审批结果
3. process_approval() → 执行/拒绝操作
4. Webhook endpoint 接收外部审批回复
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from flashsloth.core.database import get_db

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """审批请求"""
    id: int = 0
    title: str = ""                    # 审批标题
    description: str = ""              # 审批描述/详情
    action: str = ""                   # 操作类型: publish | delete | modify | custom
    target_platform: str = ""          # 目标平台
    target_url: str = ""               # 目标链接（如果有）
    requested_by: str = "system"       # 请求来源
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: str = ""
    responded_at: str = ""
    response_note: str = ""            # 管理员回复备注
    metadata: dict = field(default_factory=dict)  # 额外数据（如文章ID等）

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "action": self.action,
            "target_platform": self.target_platform,
            "target_url": self.target_url,
            "requested_by": self.requested_by,
            "status": self.status.value,
            "created_at": self.created_at,
            "responded_at": self.responded_at,
            "response_note": self.response_note,
            "metadata": self.metadata,
        }


# ─── 数据库操作 ───────────────────────

def init_approval_table():
    """确保审批表存在"""
    conn = get_db()
    try:
        conn.execute("SELECT COUNT(*) FROM approval_requests")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS approval_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                action TEXT NOT NULL DEFAULT 'custom',
                target_platform TEXT DEFAULT '',
                target_url TEXT DEFAULT '',
                requested_by TEXT DEFAULT 'system',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                responded_at TEXT,
                response_note TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            );
        """)
        conn.commit()
    finally:
        conn.close()


def create_approval(
    title: str,
    description: str = "",
    action: str = "custom",
    target_platform: str = "",
    target_url: str = "",
    requested_by: str = "system",
    metadata: dict = None,
    notify: bool = True,
) -> ApprovalRequest:
    """创建审批请求
    
    参数:
        title: 审批标题（如"发布文章到CSDN"）
        description: 审批详情
        action: 操作类型
        target_platform: 目标平台
        target_url: 目标链接
        requested_by: 请求来源
        metadata: 额外数据
        notify: 是否通过网关发送通知
    
    返回:
        ApprovalRequest
    """
    conn = get_db()
    try:
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        conn.execute(
            """INSERT INTO approval_requests 
               (title, description, action, target_platform, target_url, requested_by, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, description, action, target_platform, target_url, requested_by, meta_json)
        )
        conn.commit()
        approval_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = conn.execute("SELECT * FROM approval_requests WHERE id=?", (approval_id,)).fetchone()
        conn.close()

        req = _row_to_approval(row)

        # 通过网关发送通知
        if notify:
            _notify_approval(req)

        return req
    except Exception as e:
        conn.close()
        logger.error(f"创建审批失败: {e}")
        raise


def _notify_approval(req: ApprovalRequest):
    """通过通知网关发送审批请求"""
    try:
        from flashsloth.core.gateway import get_gateway, GatewayMessage

        gw = get_gateway()
        msg = GatewayMessage(
            title=f"📋 审批请求: {req.title}",
            body=(
                f"操作: {req.action}\n"
                f"平台: {req.target_platform or '—'}\n"
                f"详情: {req.description}\n\n"
                f"🆔 审批ID: {req.id}\n"
                f"请回复「通过 {req.id}」或「拒绝 {req.id}」"
            ),
            level="warn",
            source="approval",
            link=f"http://localhost:5000/approval/{req.id}",
        )
        results = gw.dispatch(msg)
        success = sum(1 for r in results if r.get("success"))
        logger.info(f"审批通知: 已发送到 {success}/{len(results)} 个终端")
    except Exception as e:
        logger.warning(f"审批通知发送失败（不影响审批创建）: {e}")


def process_approval(approval_id: int, approved: bool, note: str = "") -> Optional[ApprovalRequest]:
    """处理审批请求（通过或拒绝）
    
    参数:
        approval_id: 审批记录ID
        approved: True=通过, False=拒绝
        note: 管理员备注
    
    返回:
        更新后的 ApprovalRequest，若不存在则返回 None
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM approval_requests WHERE id=?", (approval_id,)).fetchone()
    if not row:
        conn.close()
        return None

    status = "approved" if approved else "rejected"
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE approval_requests SET status=?, responded_at=?, response_note=? WHERE id=?",
        (status, now, note, approval_id)
    )
    conn.commit()

    # 重新查询更新后的记录
    row = conn.execute("SELECT * FROM approval_requests WHERE id=?", (approval_id,)).fetchone()
    conn.close()

    req = _row_to_approval(row)

    # 通知管理员处理结果
    try:
        from flashsloth.core.gateway import get_gateway, GatewayMessage
        level = "success" if approved else "error"
        msg = GatewayMessage(
            title=f"{'✅' if approved else '❌'} 审批{'通过' if approved else '拒绝'}: {req.title}",
            body=f"审批ID: {req.id}\n备注: {note or '—'}",
            level=level,
            source="approval",
        )
        get_gateway().dispatch(msg)
    except Exception:
        pass

    return req


def get_pending_approvals() -> list[ApprovalRequest]:
    """获取所有待审批请求"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM approval_requests WHERE status='pending' ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return [_row_to_approval(r) for r in rows]


def get_approval_history(limit: int = 50) -> list[ApprovalRequest]:
    """获取审批历史"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM approval_requests ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [_row_to_approval(r) for r in rows]


def get_approval(approval_id: int) -> Optional[ApprovalRequest]:
    """获取单个审批请求"""
    conn = get_db()
    row = conn.execute("SELECT * FROM approval_requests WHERE id=?", (approval_id,)).fetchone()
    conn.close()
    return _row_to_approval(row) if row else None


def cancel_approval(approval_id: int) -> bool:
    """取消审批请求"""
    conn = get_db()
    row = conn.execute("SELECT * FROM approval_requests WHERE id=? AND status='pending'", (approval_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("UPDATE approval_requests SET status='cancelled', responded_at=datetime('now') WHERE id=?", (approval_id,))
    conn.commit()
    conn.close()
    return True


def _row_to_approval(row) -> ApprovalRequest:
    """数据库行转 ApprovalRequest"""
    if not row:
        return None
    # sqlite3.Row uses row["key"] not row.get()
    d = dict(row)
    try:
        meta = json.loads(d.get("metadata", "{}")) if isinstance(d.get("metadata"), str) else d.get("metadata", {})
    except (json.JSONDecodeError, TypeError):
        meta = {}
    return ApprovalRequest(
        id=d.get("id", 0),
        title=d.get("title", ""),
        description=d.get("description", ""),
        action=d.get("action", "custom"),
        target_platform=d.get("target_platform", ""),
        target_url=d.get("target_url", ""),
        requested_by=d.get("requested_by", "system"),
        status=ApprovalStatus(d.get("status", "pending")),
        created_at=d.get("created_at", ""),
        responded_at=d.get("responded_at", ""),
        response_note=d.get("response_note", ""),
        metadata=meta,
    )
