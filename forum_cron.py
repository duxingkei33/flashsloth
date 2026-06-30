"""
定时论坛任务 — 逛论坛 + 评论回复检查
由 Hermes cron 调度，直接操作 DB + forum_reader 模块
"""
import sys, os, json, re, time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/opt/data/flashsloth")
os.environ["FLASHSLOT_SKIP_AUTH"] = "1"

import sqlite3
DB = "/opt/data/flashsloth/flashsloth.db"
CST = timezone(timedelta(hours=8))

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def load_account(account_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND is_active=1",
        (account_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["config"] = json.loads(d.get("config_json", "{}"))
    return d

# mydigit.cn 技术板块（按兴趣排序）
MYDIGIT_TECH_FIDS = [
    "51",  # 拆机乐园
    "59",  # 电子学堂
    "61",  # 我爱单片机
    "66",  # 电源/充电器
    "56",  # 创意DIY
    "60",  # 维修达人
    "64",  # SSD存储技术
    "63",  # U盘存储技术
    "41",  # NAS/网络存储
    "40",  # WiFi/路由器
    "70",  # 3D打印/雕刻机
    "72",  # 仪表谈谈
]

def browse_forum(account):
    """抓取新帖 + AI筛选 + 存 DB"""
    from plugins.forum_reader import DiscuzForumReader, InterestFilter

    site_url = account["config"].get("site_url", "")
    cookies = account["config"].get("cookie", "")
    username = account["config"].get("username", account["account_name"])
    user_id = account["user_id"]

    reader = DiscuzForumReader(site_url, cookies=cookies, username=username)
    filter_engine = InterestFilter()

    if not reader.is_logged_in():
        return {"error": f"Cookie 失效，账号 {account['account_name']} 登录失败"}

    # 获取板块列表（用来映射 fid → name）
    forums = reader.get_forum_list()
    forum_map = {f["fid"]: f["name"] for f in forums}

    if not forums:
        return {"error": "无法获取板块列表"}

    # 优先级：配置 fid → 技术板块 → 前5个
    configured_fid = account["config"].get("fid", "")
    target_fids = (MYDIGIT_TECH_FIDS if "mydigit" in site_url
                   else [configured_fid] if configured_fid
                   else [f["fid"] for f in forums[:5]])

    # 只选在 forum_map 里存在的 fid
    valid_fids = [fid for fid in target_fids if fid in forum_map][:8]

    all_threads = []
    browsed_forums = []
    for fid in valid_fids:
        threads = reader.get_new_threads(fid, hours=48, max_pages=2)
        for t in threads:
            t["forum_name"] = forum_map[fid]
            t["fid"] = fid
        all_threads.extend(threads)
        browsed_forums.append(forum_map[fid])

    # AI 筛选
    filtered = filter_engine.filter_threads(all_threads)

    top_threads = []
    for t in filtered[:20]:
        detail = reader.get_thread_detail(t["tid"])
        t["content"] = detail["content"] if detail else ""
        t["author"] = detail["author"] if detail else ""
        top_threads.append(t)

    # 存 DB
    conn = get_db()
    new_count = 0
    for t in top_threads:
        existing = conn.execute(
            "SELECT id FROM forum_recommendations WHERE user_id=? AND platform=? AND tid=? AND url=?",
            (user_id, "discuz", t["tid"], t["url"])
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO forum_recommendations (user_id, platform, forum_name, title, url, tid, fid, "
            "author, content, tags, score, summary, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, "discuz", t.get("forum_name", ""), t["title"], t["url"],
             t["tid"], t.get("fid", ""), t.get("author", ""),
             t.get("content", "")[:500], json.dumps(t.get("ai_tags", [])),
             t["ai_score"], t.get("ai_summary", ""), "cron")
        )
        new_count += 1
    conn.commit()
    conn.close()

    return {
        "total": len(all_threads),
        "filtered": len(filtered),
        "new_saved": new_count,
        "forums": browsed_forums,
    }

def check_replies(account):
    """检查已发布帖子的回复"""
    from plugins.forum_reader import DiscuzForumReader

    site_url = account["config"].get("site_url", "")
    cookies = account["config"].get("cookie", "")
    username = account["config"].get("username", account["account_name"])
    user_id = account["user_id"]

    reader = DiscuzForumReader(site_url, cookies=cookies, username=username)

    conn = get_db()
    my_threads = conn.execute(
        "SELECT pl.url, pl.article_id FROM publish_log pl "
        "LEFT JOIN articles a ON pl.article_id=a.id "
        "WHERE pl.account_id=? AND pl.success=1",
        (account["id"],)
    ).fetchall()
    conn.close()

    tids = []
    for t in my_threads:
        m = re.search(r"tid=(\d+)", t["url"] or "")
        if m:
            tids.append(m.group(1))
        # 也匹配 thread-X-1-1.html 格式
        m2 = re.search(r"thread-(\d+)-", t["url"] or "")
        if not m and m2:
            tids.append(m2.group(1))

    if not tids:
        return {"new_replies": 0}

    replies = reader.get_replies_to_my_threads(tids)

    conn = get_db()
    new_count = 0
    for r in replies:
        existing = conn.execute(
            "SELECT id FROM forum_recommendations WHERE user_id=? AND platform='discuz' "
            "AND url=? AND source='cron_reply'",
            (user_id, r["url"])
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO forum_recommendations (user_id, platform, title, url, "
            "reply_author, reply_content, source, is_my_thread) VALUES (?, ?, ?, ?, ?, ?, 'cron_reply', 1)",
            (user_id, f"discuz ({r.get('author','')})",
             f"回复: {r.get('content','')[:80]}",
             r["url"], r.get("author", ""), r.get("content", "")[:200])
        )
        new_count += 1
    conn.commit()
    conn.close()

    return {"new_replies": new_count}

def main():
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"🦥 定时论坛任务 — {now}", ""]

    # mydigit.cn (account_id=4)
    account = load_account(4)
    if not account:
        print("❌ mydigit.cn 账号未找到")
        return

    lines.append(f"📡 {account['account_name']}")

    # 逛论坛
    result = browse_forum(account)
    if "error" in result:
        lines.append(f"❌ 逛论坛失败: {result['error']}")
    else:
        lines.append(f"📝 扫了 {len(result['forums'])} 个板块: "
                    f"{' | '.join(result['forums'][:4])}")
        lines.append(f"   本帖 {result['total']} 条 → 推荐 "
                    f"{result['filtered']} 条 → 新增 {result['new_saved']} 条")

    # 检查回复
    reply_result = check_replies(account)
    if reply_result["new_replies"] > 0:
        lines.append(f"💬 新回复: {reply_result['new_replies']} 条")
    else:
        lines.append("💬 新回复: 0")

    print("\n".join(lines))

if __name__ == "__main__":
    main()
