"""
💬 评论监控定时任务 — 由 Hermes cron 调度
统一采集所有论坛 + GitHub Pages (Giscus) 的评论回复

调度时段（在后台配置）：
  - 午间: 12:00-12:30 随机
  - 下午: 15:00-15:30 随机
  - 晚间: 20:00-20:30 随机
"""
import sys, os, json, re, time, random, sqlite3
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.expanduser("~"))
os.environ.setdefault("FLASHSLOTH_DB_PATH",
    os.path.expanduser("~/.hermes/flashsloth_data/flashsloth.db"))

DB_PATH = os.environ["FLASHSLOTH_DB_PATH"]
CST = timezone(timedelta(hours=8))

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def log(msg: str):
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")

def check_discuz_account(account: dict) -> dict:
    """检查一个 Discuz 论坛账号的回复"""
    from plugins.reply_monitor import ReplyMonitor
    monitor = ReplyMonitor(db_path=DB_PATH)
    result = monitor.check_account_replies(account["id"])
    monitor.close_db()
    return result

def check_giscus_account(account: dict) -> dict:
    """通过 GitHub GraphQL API 采集 Giscus 评论"""
    from sdk.adapters.giscus import GiscusAdapter

    cfg = json.loads(account.get("config_json", "{}"))
    adapter = GiscusAdapter(cfg)

    # 获取已发布到 GitHub Pages 的文章列表（通过 publish_log）
    conn = get_db()
    published = conn.execute(
        "SELECT pl.article_id, a.title, pl.url FROM publish_log pl "
        "LEFT JOIN articles a ON pl.article_id=a.id "
        "WHERE pl.account_id=? AND pl.success=1 AND pl.platform='github_pages_blog'",
        (account["id"],)
    ).fetchall()
    conn.close()

    if not published:
        return {"checked": 0, "new_replies": 0, "message": "该账号暂未发布文章到 GitHub Pages"}

    # 获取所有 Discussions 的评论
    comments = adapter.fetch_replies()
    if not comments:
        return {"checked": 0, "new_replies": 0, "total_replies": 0}

    conn = get_db()
    new_count = 0
    total = len(comments)

    for c in comments:
        # 检查是否已存在
        existing = conn.execute(
            "SELECT id FROM comment_replies WHERE "
            "platform='giscus' AND thread_tid=? AND reply_author=? AND reply_content=?",
            (c.thread_id, c.author, c.content[:200])
        ).fetchone()
        if existing:
            continue

        # 尝试匹配 article_id（通过 discussion number 在 url 中查找）
        article_id = 0
        thread_title = ""
        thread_url = ""
        for p in published:
            # 检查 URL 中是否包含文章路径
            if p["url"] and c.thread_id in p["url"]:
                article_id = p["article_id"]
                thread_title = p["title"] or ""
                thread_url = p["url"]
                break

        if not article_id:
            # 尝试从 discussion 标题/内容匹配
            continue

        conn.execute(
            "INSERT INTO comment_replies "
            "(article_id, account_id, platform, forum_name, "
            "thread_tid, thread_title, thread_url, "
            "reply_author, reply_content, reply_time, is_new, source) "
            "VALUES (?, ?, 'giscus', 'GitHub Discussions', "
            "?, ?, ?, ?, ?, ?, 1, 'auto')",
            (article_id, account["id"],
             c.thread_id, thread_title, thread_url,
             c.author, c.content[:500], c.created_at or "")
        )
        new_count += 1

    conn.commit()
    conn.close()
    return {"checked": len(comments), "new_replies": new_count, "total_replies": total}

def check_all():
    """检查所有已启用监控的论坛账号"""
    conn = get_db()

    # 1. Discuz 论坛账号（mydigit / amobbs）
    discuz_accounts = conn.execute(
        "SELECT pac.*, cmc.enabled FROM platform_accounts pac "
        "LEFT JOIN comment_monitor_config cmc ON pac.id=cmc.account_id "
        "WHERE pac.is_active=1 AND pac.platform='discuz' "
        "AND pac.config_json LIKE '%site_url%' "
        "AND (cmc.enabled IS NULL OR cmc.enabled=1)"
    ).fetchall()

    # 2. GitHub Pages (Giscus) 账号
    giscus_accounts = conn.execute(
        "SELECT pac.*, cmc.enabled FROM platform_accounts pac "
        "LEFT JOIN comment_monitor_config cmc ON pac.id=cmc.account_id "
        "WHERE pac.is_active=1 AND pac.platform='github_pages_blog' "
        "AND (cmc.enabled IS NULL OR cmc.enabled=1)"
    ).fetchall()
    conn.close()

    results = {}
    total_new = 0

    for acct in discuz_accounts:
        log(f"📡 检查 Discuz 账号: {acct['account_name']}...")
        try:
            r = check_discuz_account(dict(acct))
            n = r.get("new_replies", 0)
            total_new += n
            results[f"discuz_{acct['id']}"] = {
                "name": acct["account_name"],
                "new": n,
                "total": r.get("total_replies", 0),
                "error": r.get("error", ""),
            }
            if n > 0:
                log(f"  ✅ 发现 {n} 条新回复")
            else:
                log(f"  ℹ️ 无新回复")
        except Exception as e:
            log(f"  ❌ 异常: {e}")
            results[f"discuz_{acct['id']}"] = {"name": acct["account_name"], "error": str(e)}

    for acct in giscus_accounts:
        log(f"📡 检查 Giscus 账号: {acct['account_name']}...")
        try:
            r = check_giscus_account(dict(acct))
            n = r.get("new_replies", 0)
            total_new += n
            results[f"giscus_{acct['id']}"] = {
                "name": acct["account_name"],
                "new": n,
                "total": r.get("total_replies", 0),
                "error": r.get("error", ""),
            }
            if n > 0:
                log(f"  ✅ 发现 {n} 条新评论")
            else:
                log(f"  ℹ️ 无新评论")
        except Exception as e:
            log(f"  ❌ 异常: {e}")
            results[f"giscus_{acct['id']}"] = {"name": acct["account_name"], "error": str(e)}

    log(f"\n{'='*40}")
    log(f"📊 本次检查汇总: 共发现 {total_new} 条新回复")
    for k, v in results.items():
        if "error" in v and v["error"]:
            log(f"  ❌ {v['name']}: {v['error']}")
        elif v["new"] > 0:
            log(f"  💬 {v['name']}: {v['new']} 条新回复（共 {v['total']} 条）")
        else:
            log(f"  ✅ {v['name']}: 无新回复")
    log(f"{'='*40}\n")

    return {
        "total_new": total_new,
        "details": results,
        "time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
    }

def main():
    log("🦥 评论监控定时任务启动")
    result = check_all()
    # 输出 JSON 结果供 Hermes cron 解析
    print(f"\n---RESULT---\n{json.dumps(result, ensure_ascii=False)}\n---END---")

if __name__ == "__main__":
    main()
