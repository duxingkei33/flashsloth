"""💬 评论监控路由 — 收件箱 + API 端点"""
from flashsloth.routes._app import app
from flask import render_template, request, jsonify, g
from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.ai_provider import get_router, AIRequest
import json, re, threading, sqlite3
from datetime import datetime


# ─── 初始化 DB 表（幂等）────────────────────────
def _ensure_tables():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS comment_replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL DEFAULT 0,
            account_id INTEGER NOT NULL DEFAULT 0,
            platform TEXT NOT NULL DEFAULT '',
            forum_name TEXT NOT NULL DEFAULT '',
            thread_tid TEXT NOT NULL DEFAULT '',
            thread_title TEXT NOT NULL DEFAULT '',
            thread_url TEXT NOT NULL DEFAULT '',
            reply_author TEXT NOT NULL DEFAULT '',
            reply_content TEXT NOT NULL DEFAULT '',
            reply_time TEXT NOT NULL DEFAULT '',
            reply_pid TEXT NOT NULL DEFAULT '',
            is_new INTEGER NOT NULL DEFAULT 1,
            is_read INTEGER NOT NULL DEFAULT 0,
            is_auto_replied INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'auto',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (article_id) REFERENCES articles(id),
            FOREIGN KEY (account_id) REFERENCES platform_accounts(id)
        );
        CREATE INDEX IF NOT EXISTS idx_comment_replies_article
            ON comment_replies(article_id);
        CREATE INDEX IF NOT EXISTS idx_comment_replies_account
            ON comment_replies(account_id);
        CREATE INDEX IF NOT EXISTS idx_comment_replies_new
            ON comment_replies(is_read, created_at);

        CREATE TABLE IF NOT EXISTS comment_monitor_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1,
            slot_morning TEXT NOT NULL DEFAULT '12:00-12:30',
            slot_afternoon TEXT NOT NULL DEFAULT '15:00-15:30',
            slot_evening TEXT NOT NULL DEFAULT '20:00-20:30',
            auto_reply INTEGER NOT NULL DEFAULT 0,
            reply_style TEXT NOT NULL DEFAULT 'friendly',
            reply_tone TEXT NOT NULL DEFAULT '热心帮助',
            max_replies_per_day INTEGER NOT NULL DEFAULT 3,
            notify_replies INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (account_id) REFERENCES platform_accounts(id)
        );
    """)
    conn.commit()
    conn.close()


# ─── 页面路由 ─────────────────────────────────
@app.route("/comment-monitor")
@login_required
def comment_monitor():
    """评论监控主页"""
    _ensure_tables()
    conn = get_db()

    # 1. 论坛账号列表（带监控配置）
    discuz_accounts = conn.execute(
        "SELECT * FROM platform_accounts "
        "WHERE user_id=? AND platform='discuz' AND is_active=1 "
        "ORDER BY account_name",
        (current_user.id,)
    ).fetchall()

    # 2. 监控配置
    configs_raw = conn.execute(
        "SELECT * FROM comment_monitor_config "
        "WHERE account_id IN (SELECT id FROM platform_accounts "
        "WHERE user_id=? AND platform='discuz' AND is_active=1)",
        (current_user.id,)
    ).fetchall()
    configs = {r["account_id"]: dict(r) for r in configs_raw}

    # 3. 按板块分组的帖子回复统计
    grouped_posts = _get_grouped_stats(conn)

    # 4. 未读总数
    total_unread = conn.execute(
        "SELECT COUNT(*) as cnt FROM comment_replies cr "
        "LEFT JOIN articles a ON cr.article_id=a.id "
        "WHERE (a.user_id=? OR ?) AND cr.is_read=0",
        (current_user.id, current_user.is_admin)
    ).fetchone()["cnt"]

    conn.close()

    return render_template(
        "comment_monitor.html",
        discuz_accounts=[dict(a) for a in discuz_accounts],
        configs=configs,
        grouped=grouped_posts,
        total_unread=total_unread,
    )


def _get_grouped_stats(conn):
    """按 forum_name 分组返回帖子回复统计"""
    user_id = current_user.id
    is_admin = current_user.is_admin

    # 有回复的帖子
    rows = conn.execute("""
        SELECT
            cr.article_id,
            a.title AS article_title,
            cr.platform,
            cr.forum_name,
            cr.thread_tid,
            cr.thread_title,
            cr.thread_url,
            pa.account_name,
            pa.id AS account_id,
            COUNT(cr.id) AS reply_count,
            SUM(CASE WHEN cr.is_read=0 THEN 1 ELSE 0 END) AS unread_count,
            MAX(cr.created_at) AS last_reply_at
        FROM comment_replies cr
        LEFT JOIN articles a ON cr.article_id=a.id
        LEFT JOIN platform_accounts pa ON cr.account_id=pa.id
        WHERE (a.user_id=? OR ?)
        GROUP BY cr.article_id, cr.platform, cr.thread_tid
        ORDER BY last_reply_at DESC
    """, (user_id, is_admin)).fetchall()

    # 已发布但无回复的帖子
    no_reply = conn.execute("""
        SELECT DISTINCT
            pl.article_id,
            a.title AS article_title,
            pa.platform,
            '' AS forum_name,
            '' AS thread_tid,
            a.title AS thread_title,
            pl.url AS thread_url,
            pa.account_name,
            pa.id AS account_id
        FROM publish_log pl
        LEFT JOIN articles a ON pl.article_id=a.id
        LEFT JOIN platform_accounts pa ON pl.account_id=pa.id
        WHERE (a.user_id=? OR ?)
          AND pl.success=1
          AND pa.platform='discuz'
          AND pl.article_id NOT IN (
              SELECT DISTINCT article_id FROM comment_replies
          )
        ORDER BY pl.created_at DESC
    """, (user_id, is_admin)).fetchall()

    # 合并
    all_posts = []
    for r in rows:
        all_posts.append({
            "article_id": r["article_id"],
            "article_title": r["article_title"] or "(已删除)",
            "platform": r["platform"],
            "forum_name": r["forum_name"] or r["platform"],
            "account_name": r["account_name"] or "",
            "account_id": r["account_id"],
            "url": r["thread_url"] or "",
            "tid": r["thread_tid"],
            "reply_count": r["reply_count"],
            "unread_count": r["unread_count"],
            "last_reply_at": r["last_reply_at"] or "",
        })
    for r in no_reply:
        all_posts.append({
            "article_id": r["article_id"],
            "article_title": r["article_title"] or "(已删除)",
            "platform": r["platform"],
            "forum_name": r["forum_name"] or r["platform"],
            "account_name": r["account_name"] or "",
            "account_id": r["account_id"],
            "url": r["thread_url"] or "",
            "tid": r["thread_tid"],
            "reply_count": 0,
            "unread_count": 0,
            "last_reply_at": "",
        })

    # 按 forum_name 分组
    from collections import defaultdict
    grouped = defaultdict(list)
    for p in all_posts:
        key = p.get("forum_name") or p.get("platform") or "其他"
        grouped[key].append(p)

    return dict(grouped)


# ─── API: 检查单个论坛账号 ──────────────────────
@app.route("/api/comment-monitor/check/<int:aid>", methods=["POST"])
@login_required
def api_check_single(aid):
    """检查指定账号的回复"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    try:
        from flashsloth.plugins.reply_monitor import ReplyMonitor
        monitor = ReplyMonitor()
        result = monitor.check_account_replies(aid)
        return jsonify({
            "success": result.get("success", False),
            "new_replies": result.get("new_replies", 0),
            "total_replies": result.get("total_replies", 0),
            "checked": result.get("checked", 0),
            "error": result.get("error", ""),
            "message": result.get("message", ""),
            "needs_login": result.get("needs_login", False),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ─── API: 检查所有论坛账号 ──────────────────────
@app.route("/api/comment-monitor/check-all", methods=["POST"])
@login_required
def api_check_all():
    """检查当前用户所有论坛账号的回复"""
    conn = get_db()
    accounts = conn.execute(
        "SELECT id FROM platform_accounts "
        "WHERE user_id=? AND platform='discuz' AND is_active=1",
        (current_user.id,)
    ).fetchall()
    conn.close()

    total_new = 0
    errors = []
    for acct in accounts:
        try:
            from flashsloth.plugins.reply_monitor import ReplyMonitor
            monitor = ReplyMonitor()
            result = monitor.check_account_replies(acct["id"])
            total_new += result.get("new_replies", 0)
            if not result.get("success", True) and result.get("error"):
                errors.append(result["error"])
        except Exception as e:
            errors.append(str(e))

    return jsonify({
        "success": len(errors) == 0 or total_new > 0,
        "total_new": total_new,
        "errors": errors[:3],
        "error": "; ".join(errors[:2]) if errors else "",
    })


# ─── API: 获取帖子回复列表 ──────────────────────
@app.route("/api/comment-monitor/replies/<int:article_id>")
@login_required
def api_get_replies(article_id):
    """获取指定文章的回复列表"""
    tid = request.args.get("tid", "")
    conn = get_db()

    if tid:
        rows = conn.execute(
            "SELECT cr.* FROM comment_replies cr "
            "LEFT JOIN articles a ON cr.article_id=a.id "
            "WHERE cr.article_id=? AND cr.thread_tid=? "
            "AND (a.user_id=? OR ?) "
            "ORDER BY cr.created_at ASC",
            (article_id, tid, current_user.id, current_user.is_admin)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT cr.* FROM comment_replies cr "
            "LEFT JOIN articles a ON cr.article_id=a.id "
            "WHERE cr.article_id=? "
            "AND (a.user_id=? OR ?) "
            "ORDER BY cr.created_at ASC",
            (article_id, current_user.id, current_user.is_admin)
        ).fetchall()

    conn.close()

    replies = []
    thread_title = ""
    for r in rows:
        if not thread_title and r["thread_title"]:
            thread_title = r["thread_title"]
        replies.append({
            "id": r["id"],
            "reply_author": r["reply_author"],
            "reply_content": r["reply_content"],
            "reply_time": r["reply_time"],
            "is_new": r["is_new"],
            "is_auto_replied": r.get("is_auto_replied", 0),
            "thread_title": r["thread_title"],
            "thread_url": r["thread_url"],
            "forum_name": r["forum_name"],
            "platform": r["platform"],
        })

    return jsonify({
        "success": True,
        "replies": replies,
        "thread_title": thread_title or f"文章 #{article_id}",
        "total": len(replies),
    })


# ─── API: 标记已读 ──────────────────────────────
@app.route("/api/comment-monitor/mark-read", methods=["POST"])
@login_required
def api_mark_read():
    """标记回复为已读"""
    data = request.get_json() or {}
    conn = get_db()

    if data.get("all"):
        conn.execute(
            "UPDATE comment_replies SET is_read=1 WHERE is_read=0 "
            "AND article_id IN (SELECT id FROM articles WHERE user_id=?)",
            (current_user.id,)
        )
    elif data.get("ids"):
        ids = data["ids"]
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE comment_replies SET is_read=1 WHERE id IN ({placeholders})",
            ids
        )

    conn.commit()
    conn.close()
    return jsonify({"success": True})


# ─── API: AI 生成回复 ────────────────────────────
@app.route("/api/comment-monitor/auto-reply/<int:reply_id>", methods=["POST"])
@login_required
def api_auto_reply(reply_id):
    """AI 生成回复内容"""
    conn = get_db()
    reply = conn.execute(
        "SELECT cr.*, pa.config_json, pa.id AS account_id "
        "FROM comment_replies cr "
        "LEFT JOIN platform_accounts pa ON cr.account_id=pa.id "
        "WHERE cr.id=?",
        (reply_id,)
    ).fetchone()
    conn.close()

    if not reply:
        return jsonify({"success": False, "error": "回复不存在"})

    cfg = json.loads(reply["config_json"]) if reply["config_json"] else {}
    site_url = cfg.get("site_url", "")
    tid = reply["thread_tid"]

    # 读取监控配置中的回复风格
    conn2 = get_db()
    mon_cfg = conn2.execute(
        "SELECT * FROM comment_monitor_config WHERE account_id=?",
        (reply["account_id"],)
    ).fetchone()
    conn2.close()

    style = "friendly"
    tone = ""
    if mon_cfg:
        style = mon_cfg["reply_style"] or "friendly"
        tone = mon_cfg["reply_tone"] or ""

    # 使用 AI 生成回复
    try:
        router = get_router()
        prompt = f"""你是一个{tone or '友好'}的论坛用户，现在要回复一条对你的帖子的评论。

【帖子标题】{reply['thread_title'][:100]}
【评论者】{reply['reply_author']}
【评论内容】{reply['reply_content'][:300]}

要求：
1. 回复风格：{tone or '友好热情'}，像是真人用户在论坛交流
2. 不要过于官方或像AI，要有真人语气
3. 长度控制在200字以内
4. 自然地回应对方的评论内容
5. 不要提到"AI"、"机器人"等字眼
6. 回复完不需要加签名或分隔符

请直接输出回复内容："""

        ai_result = router.call(
            capability="writing",
            prompt=prompt,
            temperature=0.8,
            max_tokens=300,
        )

        reply_text = ""
        if ai_result and ai_result.success:
            reply_text = ai_result.content.strip()
        else:
            # fallback
            reply_text = "谢谢回复，这个思路不错，我试试看！"

        # 尝试自动提交（如果配置了自动回帖）
        auto_submitted = False
        if mon_cfg and mon_cfg["auto_reply"] and site_url:
            try:
                from flashsloth.plugins.reply_monitor import DiscuzReplyExtractor
                cookies = cfg.get("cookie", "")
                username = cfg.get("username", "")
                extractor = DiscuzReplyExtractor(site_url, cookies=cookies, username=username)
                submit_ok = _submit_reply_to_forum(extractor, tid, reply_text)
                if submit_ok:
                    auto_submitted = True
                    # 标记已自动回复
                    conn3 = get_db()
                    conn3.execute(
                        "UPDATE comment_replies SET is_auto_replied=1 WHERE id=?",
                        (reply_id,)
                    )
                    conn3.commit()
                    conn3.close()
            except Exception:
                pass

        return jsonify({
            "success": True,
            "reply_text": reply_text,
            "tid": tid,
            "account_id": reply["account_id"],
            "site_url": site_url,
            "auto_submitted": auto_submitted,
            "message": "🤖 已自动回复到论坛" if auto_submitted else "",
        })

    except Exception as e:
        # fallback
        return jsonify({
            "success": True,
            "reply_text": "谢谢回复！这个思路很好，我回头试试看。",
            "tid": tid,
            "account_id": reply["account_id"],
            "site_url": site_url,
            "auto_submitted": False,
        })


def _submit_reply_to_forum(extractor, tid: str, reply_text: str) -> bool:
    """尝试通过 HumanSession 提交回复到论坛"""
    try:
        # 构造回复表单
        form_url = f"/forum.php?mod=post&action=reply&tid={tid}&extra=&replysubmit=yes"
        data = {
            "message": reply_text,
            "replysubmit": "yes",
            "posttime": str(int(datetime.now().timestamp())),
        }
        r = extractor.browser.session.post(
            extractor.site_url + form_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        # 检查是否成功（页面不包含错误信息即可）
        if r.status_code == 200 and "error" not in r.url.lower():
            return True
        return False
    except Exception:
        return False


# ─── API: 提交回复到论坛 ────────────────────────
@app.route("/api/comment-monitor/reply-submit", methods=["POST"])
@login_required
def api_reply_submit():
    """将 AI 生成的回复提交到论坛"""
    data = request.get_json() or {}
    tid = data.get("tid", "")
    reply_text = data.get("reply_text", "")
    account_id = data.get("account_id", 0)

    if not tid or not reply_text:
        return jsonify({"success": False, "error": "缺少必要参数"})

    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=?",
        (account_id,)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    site_url = cfg.get("site_url", "")
    cookies = cfg.get("cookie", "")
    username = acct["account_name"]

    try:
        from flashsloth.plugins.reply_monitor import DiscuzReplyExtractor
        extractor = DiscuzReplyExtractor(site_url, cookies=cookies, username=username)

        if not extractor.is_logged_in():
            return jsonify({
                "success": False,
                "error": "Cookie 已过期，请重新登录",
                "need_human": True,
            })

        ok = _submit_reply_to_forum(extractor, tid, reply_text)
        if ok:
            return jsonify({"success": True, "message": "回复成功"})
        else:
            return jsonify({
                "success": False,
                "error": "回复提交失败，可能是论坛拦截了自动回复",
                "need_human": True,
            })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"提交异常: {str(e)}",
            "need_human": True,
        })


# ─── API: 保存监控配置 ──────────────────────────
@app.route("/api/comment-monitor/config/<int:aid>", methods=["POST"])
@login_required
def api_save_config(aid):
    """保存指定论坛账号的监控配置"""
    data = request.get_json() or {}

    # 验证账号所有权
    conn = get_db()
    acct = conn.execute(
        "SELECT id FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()

    if not acct:
        conn.close()
        return jsonify({"success": False, "error": "账号不存在"})

    # UPSERT
    conn.execute("""
        INSERT INTO comment_monitor_config
            (account_id, enabled, slot_morning, slot_afternoon, slot_evening,
             auto_reply, reply_style, reply_tone, max_replies_per_day, notify_replies)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(account_id) DO UPDATE SET
            enabled=excluded.enabled,
            slot_morning=excluded.slot_morning,
            slot_afternoon=excluded.slot_afternoon,
            slot_evening=excluded.slot_evening,
            auto_reply=excluded.auto_reply,
            reply_style=excluded.reply_style,
            reply_tone=excluded.reply_tone,
            max_replies_per_day=excluded.max_replies_per_day,
            notify_replies=excluded.notify_replies,
            updated_at=datetime('now')
    """, (
        aid,
        int(data.get("enabled", 1)),
        data.get("slot_morning", "12:00-12:30"),
        data.get("slot_afternoon", "15:00-15:30"),
        data.get("slot_evening", "20:00-20:30"),
        int(data.get("auto_reply", 0)),
        data.get("reply_style", "friendly"),
        data.get("reply_tone", "热心帮助"),
        int(data.get("max_replies_per_day", 3)),
        int(data.get("notify_replies", 1)),
    ))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "配置已保存"})


# ─── 初始化（模块导入时执行）────────────────────
_ensure_tables()
