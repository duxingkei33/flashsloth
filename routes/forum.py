"""FlashSloth Forum Reader Routes — 论坛推荐/浏览/回复"""
from flashsloth.routes._app import app

from flask import render_template, request, jsonify
import json, time

from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.publisher import list_publishers

from flashsloth.plugins.forum_reader import DiscuzForumReader, InterestFilter

# 论坛类平台名称集合（数据驱动：可从配置扩展）
_FORUM_PLATFORMS = {"discuz", "amobbs", "mydigit"}

_interest_filter = InterestFilter()

@app.route("/forum-reader")
@login_required
def forum_reader():
   """AI逛论坛 — 推荐 + 浏览 + 回复汇总"""
   conn = get_db()
   # 获取最近推荐
   recs = conn.execute(
       "SELECT * FROM forum_recommendations WHERE user_id=? "
       "ORDER BY score DESC, created_at DESC LIMIT 100",
       (current_user.id,)
   ).fetchall()
   # 获取用户已配置的论坛类平台账号
   all_active = conn.execute(
       "SELECT * FROM platform_accounts WHERE user_id=? AND is_active=1",
       (current_user.id,)
   ).fetchall()
   discuz_accounts = [a for a in all_active if a["platform"] in _FORUM_PLATFORMS]
   # 统计未读
   unread = conn.execute(
       "SELECT COUNT(*) FROM forum_recommendations WHERE user_id=? AND is_read=0",
       (current_user.id,)
   ).fetchone()[0]
   conn.close()
   return render_template("forum_reader.html",
                        recommendations=[dict(r) for r in recs],
                        discuz_accounts=[dict(a) for a in discuz_accounts],
                        unread=unread,
                        publishers=list_publishers())

@app.route("/api/forum-reader/browse", methods=["POST"])
@login_required
def api_forum_browse():
   """浏览指定论坛并抓取新帖"""
   account_id = request.json.get("account_id")
   hours = request.json.get("hours", 24)
   if not account_id:
       return jsonify({"success": False, "error": "请选择论坛账号"})
   account_id = int(account_id)
   hours = int(hours)

   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (account_id, current_user.id)
   ).fetchone()
   conn.close()

   if not acct:
       return jsonify({"success": False, "error": "账号不存在"})

   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   site_url = cfg.get("site_url", "")
   cookies = cfg.get("cookie", "")
   username = cfg.get("username", acct["account_name"])

   if not site_url:
       return jsonify({"success": False, "error": "论坛地址未配置"})

   reader = DiscuzForumReader(site_url, cookies=cookies, username=username)

   # 获取板块列表
   forums = reader.get_forum_list()
   if not forums:
       return jsonify({"success": False, "error": "无法获取板块列表，请检查 Cookie 是否有效"})

   # 遍历板块抓取新帖
   all_threads = []
   for f in forums[:5]:  # 限制前5个板块
       threads = reader.get_new_threads(f["fid"], hours=hours, max_pages=2)
       for t in threads:
           t["forum_name"] = f["name"]
       all_threads.extend(threads)

   # AI 筛选
   filtered = _interest_filter.filter_threads(all_threads)

   # 获取详细内容（对高分帖子）
   top_threads = []
   for t in filtered[:20]:
       detail = reader.get_thread_detail(t["tid"])
       t["content"] = detail["content"] if detail else ""
       t["author"] = detail["author"] if detail else ""
       top_threads.append(t)

   # 存入数据库
   conn = get_db()
   platform_name = acct["platform"]  # 数据驱动：使用实际平台名
   new_count = 0
   for t in top_threads:
       # 去重
       existing = conn.execute(
           "SELECT id FROM forum_recommendations WHERE user_id=? AND platform=? AND tid=? AND url=?",
           (current_user.id, platform_name, t["tid"], t["url"])
       ).fetchone()
       if existing:
           continue
       conn.execute(
           "INSERT INTO forum_recommendations (user_id, platform, forum_name, title, url, tid, fid, "
           "author, content, tags, score, summary, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
           (current_user.id, platform_name, t.get("forum_name", ""), t["title"], t["url"],
            t["tid"], t.get("fid", ""), t.get("author", ""),
            t.get("content", "")[:500], json.dumps(t.get("ai_tags", [])),
            t["ai_score"], t.get("ai_summary", ""), "keyword")
       )
       new_count += 1
   conn.commit()
   conn.close()

   return jsonify({
       "success": True,
       "total": len(all_threads),
       "filtered": len(filtered),
       "new_saved": new_count,
       "forums": [f["name"] for f in forums],
       "samples": top_threads[:5],
   })

@app.route("/api/forum-reader/replies", methods=["POST"])
@login_required
def api_forum_replies():
   """检查我的帖子的回复"""
   account_id = request.json.get("account_id")
   if not account_id:
       return jsonify({"success": False, "error": "请选择论坛账号"})
   account_id = int(account_id)

   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (account_id, current_user.id)
   ).fetchone()

   # 查找当前用户在该论坛已发布的帖子
   my_threads = conn.execute(
       "SELECT pl.url, pl.article_id FROM publish_log pl "
       "LEFT JOIN articles a ON pl.article_id=a.id "
       "WHERE pl.account_id=? AND pl.success=1 AND a.user_id=?",
       (account_id, current_user.id)
   ).fetchall()
   conn.close()

   if not acct:
       return jsonify({"success": False, "error": "账号不存在"})

   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   site_url = cfg.get("site_url", "")
   cookies = cfg.get("cookie", "")
   username = cfg.get("username", acct["account_name"])

   reader = DiscuzForumReader(site_url, cookies=cookies, username=username)

   # 从发布记录中提取 tid
   tids = []
   for t in my_threads:
       m = re.search(r"tid=(\d+)", t["url"] or "")
       if m:
           tids.append(m.group(1))

   replies = reader.get_replies_to_my_threads(tids)

   # 存入数据库（标记为我的帖子回复）
   conn = get_db()
   platform_name = acct["platform"] if acct else "discuz"
   new_count = 0
   for r in replies:
       existing = conn.execute(
           "SELECT id FROM forum_recommendations WHERE user_id=? AND platform=? "
           "AND url=? AND source='reply'",
           (current_user.id, platform_name, r["url"])
       ).fetchone()
       if existing:
           continue
       conn.execute(
           "INSERT INTO forum_recommendations (user_id, platform, title, url, "
           "reply_author, reply_content, source, is_my_thread) VALUES (?, ?, ?, ?, ?, ?, 'reply', 1)",
           (current_user.id, platform_name, f"回复: {r.get('content','')[:80]}",
            r["url"], r.get("author", ""), r.get("content", "")[:200])
       )
       new_count += 1
   conn.commit()
   conn.close()

   return jsonify({
       "success": True,
       "new_replies": new_count,
       "total_replies": len(replies),
   })

@app.route("/api/forum-reader/mark-read/<int:rid>")
@login_required
def api_forum_mark_read(rid):
   """标记推荐为已读"""
   conn = get_db()
   conn.execute(
       "UPDATE forum_recommendations SET is_read=1 WHERE id=? AND user_id=?",
       (rid, current_user.id)
   )
   conn.commit()
   conn.close()
   return jsonify({"success": True})

@app.route("/api/forum-reader/get-forums/<int:account_id>")
@login_required
def api_get_forums(account_id):
   """获取 Discuz 论坛板块列表"""
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (account_id, current_user.id)
   ).fetchone()
   conn.close()

   if not acct:
       return jsonify({"success": False, "error": "账号不存在"})

   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   site_url = cfg.get("site_url", "")
   cookies = cfg.get("cookie", "")
   username = cfg.get("username", acct["account_name"])

   if not site_url:
       return jsonify({"success": False, "error": "论坛地址未配置"})

   reader = DiscuzForumReader(site_url, cookies=cookies, username=username)
   forums = reader.get_forum_list()

   return jsonify({"success": True, "forums": forums})

@app.route("/api/forum-reader/clear-old")
@login_required
def api_forum_clear_old():
   """清理7天前的已读推荐"""
   conn = get_db()
   deleted = conn.execute(
       "DELETE FROM forum_recommendations WHERE user_id=? AND is_read=1 "
       "AND created_at < datetime('now', '-7 days')",
       (current_user.id,)
   ).rowcount
   conn.commit()
   conn.close()
   return jsonify({"success": True, "deleted": deleted})

