"""
💬 评论监控引擎 — FlashSloth 插件
定时检查各论坛我发布的帖子是否有新回复。
使用 HumanSession 模拟真人浏览器，自动抓取回复数据。

核心功能：
1. 采集指定帖子的所有回复
2. 识别新回复（去重）
3. AI 生成智能回帖
4. 多论坛统一管理（mydigit / amobbs / csdn 等）
"""
import re, json, time, random
from datetime import datetime, timedelta
from html import unescape
from typing import Optional

try:
    from flashsloth.plugins.browser_session import HumanSession
except ImportError:
    from plugins.browser_session import HumanSession

# ─── 论坛特定提取器 ──────────────────────────────

class DiscuzReplyExtractor:
    """Discuz! 引擎的回复提取器（兼容 mydigit / amobbs 等）"""

    def __init__(self, site_url: str, cookies: str = "", username: str = ""):
        self.site_url = site_url.rstrip("/")
        self.browser = HumanSession(base_url=site_url, min_delay=0.8, max_delay=2.5)
        if cookies:
            self.browser.set_cookies(cookies)
        self.username = username
        self._my_tids_cache = {}  # tid -> thread_info

    def is_logged_in(self) -> bool:
        """检查登录状态"""
        try:
            r = self.browser.get("/home.php?mod=space&do=profile")
            if self.username and self.username in r.text:
                return True
            for c in self.browser.session.cookies:
                if "auth" in c.name.lower():
                    return True
            return "login" not in r.url.lower() and len(r.text) > 2000
        except:
            return False

    def get_replies_for_thread(self, tid: str) -> list[dict]:
        """获取指定帖子的所有回复（去重、识别自己）"""
        replies = []
        try:
            # 用多种 URL 格式尝试
            urls = [
                f"/forum.php?mod=viewthread&tid={tid}",
                f"/thread-{tid}-1-1.html",
                f"/forum.php?mod=viewthread&tid={tid}&extra=&ordertype=1",
            ]
            resp = None
            for u in urls:
                try:
                    resp = self.browser.get(u)
                    if resp and len(resp.text) > 2000:
                        break
                except:
                    continue
            if not resp or len(resp.text) < 2000:
                return replies

            html = resp.text

            # ── 提取帖子标题 ──
            title = ""
            for pat in [
                r'<title>([^<]+)</title>',
                r'id="thread_subject"[^>]*>([^<]+)<',
                r'<span[^>]*id="thread_subject"[^>]*>([^<]+)<',
            ]:
                m = re.search(pat, html)
                if m:
                    title = unescape(m.group(1)).strip()
                    # 去掉 Discuz 论坛名后缀
                    title = re.sub(r'\s*-\s*[^-]+$', '', title).strip()
                    break

            # ── 提取论坛板块名 ──
            forum_name = ""
            for pat in [
                r'<a[^>]*href="[^"]*forumdisplay\?fid=\d+"[^>]*>([^<]+)</a>',
                r'<em>[^<]*<a[^>]*>([^<]+)</a>[^<]*</em>',
            ]:
                for m2 in re.finditer(pat, html):
                    name = unescape(m2.group(1)).strip()
                    if name and len(name) < 20 and "首页" not in name and "论坛" not in name:
                        forum_name = name
                        break
                if forum_name:
                    break

            # ── 提取所有回复楼层 ──
            # Discuz 楼层结构: div.plc (或 div.pls + div.pcb)
            post_blocks = re.finditer(
                r'<div[^>]*id="post_(\d+)"[^>]*>.*?'
                r'<div[^>]*class="pi"[^>]*>.*?'
                r'<a[^>]*class="xw1"[^>]*>([^<]+)</a>.*?'
                r'<td[^>]*class="t_f"[^>]*>(.*?)</td>',
                html, re.DOTALL
            )

            seen_authors = set()
            for m in post_blocks:
                pid = m.group(1)
                author = unescape(m.group(2)).strip()
                content_raw = m.group(3)
                content = unescape(re.sub(r"<[^>]+>", " ", content_raw)).strip()
                content = re.sub(r"\s+", " ", content)[:500]

                if not content or len(content) < 5:
                    continue
                if author == self.username:
                    continue  # 跳过自己

                # 去重
                dedup_key = f"{author}:{content[:80]}"
                if dedup_key in seen_authors:
                    continue
                seen_authors.add(dedup_key)

                # 提取回复时间
                reply_time = ""
                for tp in [
                    r'<em[^>]*id="authorposton\d*"[^>]*>(.*?)</em>',
                    r'<span[^>]*title="[^"]*">(\d{4}[-:]\d{2}[-:]\d{2}[^<]*)</span>',
                ]:
                    tm = re.search(tp, html[html.find(f'post_{pid}'):][:2000])
                    if tm:
                        reply_time = unescape(re.sub(r"<[^>]+>", "", tm.group(1))).strip()
                        break

                replies.append({
                    "pid": pid,
                    "author": author,
                    "content": content,
                    "time": reply_time,
                    "is_self": False,
                })

            # ── 备选方案：用更宽松的正则（兼容 mydigit.cn 等不同模板） ──
            if len(replies) == 0:
                # 用 reply_author: reply_content 模式
                blocks = re.findall(
                    r'<div[^>]*class="plc"[^>]*>(.*?)</div>\s*</div>',
                    html, re.DOTALL
                )
                for i, block in enumerate(blocks):
                    if i == 0:
                        continue  # 跳过主楼
                    author = ""
                    m = re.search(r'<a[^>]*class="xw1"[^>]*>([^<]+)</a>', block)
                    if m:
                        author = unescape(m.group(1)).strip()
                    content_raw = re.sub(r"<[^>]+>", " ", block)[:600].strip()
                    if not author or not content_raw or len(content_raw) < 5:
                        continue
                    if author == self.username:
                        continue
                    dedup_key = f"{author}:{content_raw[:80]}"
                    if dedup_key in seen_authors:
                        continue
                    seen_authors.add(dedup_key)
                    replies.append({
                        "pid": "",
                        "author": author,
                        "content": content_raw[:300],
                        "time": "",
                        "is_self": False,
                    })

            return {
                "tid": tid,
                "title": title or f"帖子 {tid}",
                "forum_name": forum_name or "",
                "replies": replies,
                "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
            }

        except Exception as e:
            return {
                "tid": tid,
                "title": "",
                "forum_name": "",
                "replies": replies,
                "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                "error": str(e),
            }

    def get_my_thread_tids(self, publish_logs: list[dict]) -> list[str]:
        """从发布日志中提取帖子 TID"""
        tids = []
        for log in publish_logs:
            url = log.get("url", "") or ""
            m = re.search(r"tid=(\d+)", url)
            if m:
                tids.append(m.group(1))
            m2 = re.search(r"thread-(\d+)-", url)
            if not m and m2:
                tids.append(m2.group(1))
        return list(set(tids))


# ─── 回复监控管理器 ──────────────────────────────

class ReplyMonitor:
    """多论坛回复监控的统一入口"""

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or ""
        self._conn = None

    def get_db(self):
        if self._conn is None:
            import sqlite3
            # 使用环境变量或默认路径
            if self.db_path:
                db = self.db_path
            else:
                db = os.environ.get(
                    "FLASHSLOTH_DB_PATH",
                    "/home/duxingkei/.hermes/flashsloth_data/flashsloth.db"
                )
            self._conn = sqlite3.connect(db, timeout=15)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close_db(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_published_threads(self, account_id: int) -> list[dict]:
        """获取某个账号已发布的帖子列表"""
        conn = self.get_db()
        rows = conn.execute(
            "SELECT pl.*, a.title as article_title FROM publish_log pl "
            "LEFT JOIN articles a ON pl.article_id=a.id "
            "WHERE pl.account_id=? AND pl.success=1 "
            "ORDER BY pl.created_at DESC",
            (account_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def check_account_replies(self, account_id: int) -> dict:
        """检查指定账号所有帖子的回复"""
        conn = self.get_db()
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE id=? AND is_active=1",
            (account_id,)
        ).fetchone()
        if not acct:
            return {"success": False, "error": "账号不存在或已禁用"}

        acct_dict = dict(acct)
        cfg = json.loads(acct_dict.get("config_json", "{}"))

        site_url = cfg.get("site_url", "")
        cookies = cfg.get("cookie", "")
        username = cfg.get("username", acct_dict["account_name"])

        if not site_url:
            return {"success": False, "error": "论坛地址未配置"}

        # 获取已发布的帖子
        threads = self.get_published_threads(account_id)
        if not threads:
            return {"success": True, "checked": 0, "new_replies": 0,
                    "total_replies": 0, "message": "该账号暂未发布帖子"}

        extractor = DiscuzReplyExtractor(site_url, cookies=cookies, username=username)

        # 检查登录状态
        if not extractor.is_logged_in():
            return {"success": False, "error": "Cookie 已过期，请重新登录",
                    "needs_login": True}

        # 提取所有 TID
        tids = extractor.get_my_thread_tids(threads)
        if not tids:
            return {"success": True, "checked": 0, "new_replies": 0,
                    "total_replies": 0, "message": "无法从发布记录提取帖子ID"}

        # 为每个帖子创建 article_id 映射
        tid_to_article = {}
        for t in threads:
            url = t.get("url", "") or ""
            m = re.search(r"tid=(\d+)", url)
            if m:
                tid_to_article[m.group(1)] = t["article_id"]
            m2 = re.search(r"thread-(\d+)-", url)
            if not m and m2:
                tid_to_article[m2.group(1)] = t["article_id"]

        total_new = 0
        total_found = 0
        checked_count = 0
        thread_results = []

        for tid in tids:
            # 模拟真人延迟
            time.sleep(random.uniform(1.0, 3.0))

            result = extractor.get_replies_for_thread(tid)
            checked_count += 1
            thread_replies = result.get("replies", [])
            article_id = tid_to_article.get(tid, 0)
            thread_url = result.get("url", f"{site_url}/forum.php?mod=viewthread&tid={tid}")
            thread_title = result.get("title", f"帖子 {tid}")
            forum_name = result.get("forum_name", "")

            total_found += len(thread_replies)

            for reply in thread_replies:
                # 去重：检查是否已存在
                existing = conn.execute(
                    "SELECT id FROM comment_replies WHERE "
                    "article_id=? AND account_id=? AND thread_tid=? "
                    "AND reply_author=? AND reply_content=?",
                    (article_id, account_id, tid,
                     reply["author"], reply["content"][:200])
                ).fetchone()
                if existing:
                    continue

                # 新回复，存入
                conn.execute(
                    "INSERT INTO comment_replies "
                    "(article_id, account_id, platform, forum_name, "
                    "thread_tid, thread_title, thread_url, "
                    "reply_author, reply_content, reply_time, reply_pid, is_new) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (article_id, account_id, acct_dict["platform"],
                     forum_name, tid, thread_title, thread_url,
                     reply["author"], reply["content"][:500],
                     reply.get("time", ""), reply.get("pid", ""))
                )
                total_new += 1

            thread_results.append({
                "tid": tid,
                "article_id": article_id,
                "title": thread_title,
                "replies_found": len(thread_replies),
                "new": len([r for r in thread_replies
                           if not conn.execute(
                               "SELECT id FROM comment_replies WHERE "
                               "article_id=? AND account_id=? AND thread_tid=? "
                               "AND reply_author=? AND reply_content=?",
                               (article_id, account_id, tid,
                                r["author"], r["content"][:200])
                           ).fetchone()]),
            })

        conn.commit()

        return {
            "success": True,
            "checked": checked_count,
            "new_replies": total_new,
            "total_replies": total_found,
            "threads": thread_results,
        }

    def check_all_accounts(self) -> list[dict]:
        """检查所有启用监控的账号"""
        conn = self.get_db()
        accounts = conn.execute(
            "SELECT pac.id, cmc.enabled, cmc.notify_replies "
            "FROM platform_accounts pac "
            "LEFT JOIN comment_monitor_config cmc ON pac.id=cmc.account_id "
            "WHERE pac.is_active=1 AND pac.platform='discuz' "
            "AND (cmc.enabled IS NULL OR cmc.enabled=1)"
        ).fetchall()

        results = []
        for acct in accounts:
            result = self.check_account_replies(acct["id"])
            results.append({
                "account_id": acct["id"],
                **result,
            })
        return results

    def get_stats(self) -> dict:
        """获取所有论坛的评论统计（用于页面展示）"""
        conn = self.get_db()
        # 按 article 分组统计
        stats = conn.execute(
            "SELECT a.id as article_id, a.title as article_title, "
            "cr.platform, cr.forum_name, cr.thread_tid, "
            "cr.thread_title, cr.thread_url, "
            "COUNT(cr.id) as reply_count, "
            "SUM(CASE WHEN cr.is_read=0 THEN 1 ELSE 0 END) as unread_count, "
            "MAX(cr.created_at) as last_reply_at "
            "FROM comment_replies cr "
            "LEFT JOIN articles a ON cr.article_id=a.id "
            "GROUP BY cr.article_id, cr.platform, cr.thread_tid "
            "ORDER BY last_reply_at DESC"
        ).fetchall()

        # 所有已发布到论坛的帖子（含无回复的）
        all_posts = conn.execute(
            "SELECT pl.article_id, a.title as article_title, "
            "pl.platform, pl.url, pa.account_name, "
            "pa.id as account_id, pa.config_json "
            "FROM publish_log pl "
            "LEFT JOIN articles a ON pl.article_id=a.id "
            "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
            "WHERE pl.success=1 AND pa.platform='discuz' "
            "GROUP BY pl.article_id, pa.id "
            "ORDER BY pl.created_at DESC"
        ).fetchall()

        # 提取帖子ID
        all_forum_posts = []
        for p in all_posts:
            cfg = json.loads(p["config_json"]) if p["config_json"] else {}
            site_url = cfg.get("site_url", "")
            url = p["url"] or ""
            tid = ""
            m = re.search(r"tid=(\d+)", url)
            if m:
                tid = m.group(1)
            m2 = re.search(r"thread-(\d+)-", url)
            if not m and m2:
                tid = m2.group(1)

            all_forum_posts.append({
                "article_id": p["article_id"],
                "article_title": p["article_title"] or "(已删除)",
                "platform": p["platform"],
                "account_name": p["account_name"],
                "account_id": p["account_id"],
                "url": url,
                "tid": tid,
                "site_url": site_url,
            })

        conn.close()
        return {
            "stats": [dict(s) for s in stats],
            "all_posts": all_forum_posts,
        }


# ─── 智能回帖引擎 ────────────────────────────────

class AutoReplyEngine:
    """AI 驱动的自动回帖引擎，模拟真人操作"""

    # 回帖风格模板
    REPLY_STYLES = {
        "friendly": {
            "tone": "友好热情",
            "max_length": 200,
            "patterns": ["谢谢分享", "学习了", "不错", "支持"],
        },
        "helpful": {
            "tone": "热心帮助",
            "max_length": 300,
            "patterns": ["试试看", "建议", "可以参考"],
        },
        "technical": {
            "tone": "技术讨论",
            "max_length": 400,
            "patterns": ["根据文档", "实测发现", "说明"],
        },
        "casual": {
            "tone": "随意闲聊",
            "max_length": 150,
            "patterns": ["哈哈", "确实", "有意思"],
        },
    }

    def __init__(self, ai_provider=None):
        self.ai_provider = ai_provider

    def generate_reply(self, thread_title: str, thread_content: str,
                       reply_content: str, reply_author: str,
                       style: str = "friendly", tone: str = "") -> str:
        """AI 生成自然回复"""
        style_cfg = self.REPLY_STYLES.get(style, self.REPLY_STYLES["friendly"])
        tone_desc = tone or style_cfg["tone"]
        max_len = style_cfg["max_length"]

        # 构建提示词
        prompt = f"""你是一个{style_cfg['tone']}的论坛用户，现在要回复一条对你帖子的评论。

【你的帖子标题】{thread_title[:100]}
【帖子内容摘要】{thread_content[:200]}
【评论者】{reply_author}
【评论内容】{reply_content[:300]}

要求：
1. 回复风格：{tone_desc}，像是真人用户在论坛交流
2. 不要过于官方或像AI，要有真人语气
3. 长度控制在{max_len}字以内
4. 自然地回应对方的评论内容
5. 不要提到"AI"、"机器人"等字眼
6. 如果是技术问题，给出切实可行的建议
7. 回复完不需要加签名或分隔符

请直接输出回复内容："""

        try:
            if self.ai_provider:
                result = self.ai_provider.call(
                    capability="writing",
                    prompt=prompt,
                    temperature=0.8,
                    max_tokens=max_len,
                )
                reply = result.content.strip() if result.success else ""
            else:
                # 无AI Provider时的备选——从模式库选
                reply = self._template_reply(reply_content, style)

            if not reply:
                reply = self._template_reply(reply_content, style)

            # 后处理：确保像真人
            reply = self._humanize(reply)
            return reply[:max_len]

        except Exception:
            return self._template_reply(reply_content, style)

    def _template_reply(self, reply_content: str, style: str = "friendly") -> str:
        """无AI时的模板回复"""
        templates = {
            "friendly": [
                "谢谢回复，这个思路不错，我试试看！",
                "感谢分享经验，学到了！",
                "嗯嗯，确实是这样，多谢指点~",
                "好的，我回头试试你说的方案。",
            ],
            "helpful": [
                "感谢反馈，这个问题我之前也遇到过，可以试试重启一下。",
                "谢谢提醒，我按你说的检查了一下，确实有这个问题。",
                "好的，我去看看，多谢建议！",
            ],
            "technical": [
                "谢谢回复，根据我的测试，这个参数确实有影响。",
                "嗯，文档里也是这么说的，实测有效。",
                "补充一下，这个和固件版本也有关系。",
            ],
            "casual": [
                "哈哈，有意思！",
                "确实，我也这么觉得。",
                "不错不错，收藏了~",
            ],
        }
        pool = templates.get(style, templates["friendly"])
        return random.choice(pool)

    def _humanize(self, text: str) -> str:
        """后处理让文本更像真人"""
        # 移除AI常见标志
        text = re.sub(r'(?i)\bas (an? )?(AI|language model|assistant|robot)\b', '', text)
        text = re.sub(r'(?i)I (am|was) (an? )?(AI|language model)', '', text)
        text = re.sub(r'(?i)(作为|我是一个)(AI|人工智能|语言模型|机器人)', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        # 确保以中文标点结尾
        if text and text[-1] not in '。！？~.:!?~\n':
            text += '。'
        return text


try:
    import os as _os
except ImportError:
    pass
