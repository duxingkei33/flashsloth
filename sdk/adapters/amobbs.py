"""
阿莫论坛 (amobbs.com) 平台适配器

基于 Discuz! 引擎，复用 DiscuzPublisher 发帖、DiscuzForumReader 采集。

能力清单：
  - sign_in()             签到（不支持）
  - publish()             发布帖子 ✅
  - retract()             撤回（不支持）
  - fetch_posts()         采集新帖 ✅
  - fetch_replies()       采集回复 ✅
  - fetch_thread_detail() 读帖详情 ✅
  - reply_comment()       回复评论 ✅
  - browse_forum()        逛论坛 ✅
  - deploy()              部署（不支持）
"""
from typing import Optional
import re
import time
import random

from ..adapter import PlatformAdapter, register, Article, Comment


@register
class AmobbsAdapter(PlatformAdapter):
    name = "amobbs"
    display_name = "阿莫论坛"
    site_url = "https://www.amobbs.com"
    version = "1.0.0"
    description = "阿莫电子论坛 — 中国电子工程师社区"
    icon = "🔧"

    config_fields = [
        {"key": "site_url", "label": "论坛地址", "type": "text", "required": True,
         "default": "https://www.amobbs.com",
         "placeholder": "https://www.amobbs.com"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": False,
         "placeholder": "登录后从浏览器 F12 复制 Cookie"},
        {"key": "username", "label": "用户名", "type": "text", "required": False,
         "placeholder": "论坛登录用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": False,
         "placeholder": "论坛登录密码"},
        {"key": "fid", "label": "版块 ID", "type": "text", "required": False,
         "placeholder": "目标版块 ID（如 2）"},
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        if not self.config.get("site_url"):
            self.config["site_url"] = "https://www.amobbs.com"

    # ─── 签到 ─────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """阿莫论坛 k_misign 未启用，不支持自动签到"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────
    def publish(self, article: Article, **kwargs) -> dict:
        """发布帖子到阿莫论坛，使用 DiscuzPublisher 的 cookie 模式"""
        from plugins.publisher_discuz import DiscuzPublisher
        publisher = DiscuzPublisher(self.config)
        return publisher.publish(article, **kwargs)

    # ─── 撤回 ─────────────────────────────────
    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """阿莫论坛暂不支持撤回已发布的帖子"""
        return {"supported": False}

    # ─── 采集帖子 ─────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """从阿莫论坛采集新帖子"""
        from plugins.forum_reader import DiscuzForumReader
        site_url = self.config.get("site_url", "https://www.amobbs.com").rstrip("/")
        cookie = self.config.get("cookie", "")
        username = self.config.get("username", "")
        password = self.config.get("password", "")

        reader = DiscuzForumReader(
            site_url=site_url, cookies=cookie,
            username=username, password=password,
        )

        fid = kwargs.get("fid") or self.config.get("fid")
        if not fid:
            return []

        threads = reader.get_new_threads(fid, hours=hours, max_pages=max_pages)
        articles = []
        for t in threads:
            detail = reader.get_thread_detail(t["tid"])
            content = detail.get("content", "") if detail else ""
            author = detail.get("author", "") if detail else t.get("author", "")
            article = Article(
                title=t["title"],
                body=content,
                source=self.name,
                source_url=t.get("url", ""),
                source_id=t["tid"],
                author=author,
                raw=t,
            )
            articles.append(article)
        return articles

    # ─── 采集回复 ─────────────────────────────
    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """采集指定帖子的回复"""
        if not thread_ids:
            return []
        try:
            from plugins.forum_reader import DiscuzForumReader
            site_url = self.config.get("site_url", "https://www.amobbs.com").rstrip("/")
            reader = DiscuzForumReader(
                site_url=site_url,
                cookies=self.config.get("cookie", ""),
                username=self.config.get("username", ""),
                password=self.config.get("password", ""),
            )
            raw_replies = reader.get_replies_to_my_threads(
                my_thread_tids=thread_ids,
                max_pages=kwargs.get("max_pages", 2),
            )
            comments = []
            for r in raw_replies:
                comment = Comment(
                    id="",
                    author=r.get("author", ""),
                    content=r.get("content", ""),
                    created_at=None,
                    parent_id="",
                    thread_id=r.get("thread_tid", ""),
                )
                comments.append(comment)
            return comments
        except Exception as e:
            return []

    # ─── 读帖详情 ─────────────────────────────
    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """获取单篇帖子的详细内容"""
        if not thread_id:
            return None
        try:
            from plugins.forum_reader import DiscuzForumReader
            site_url = self.config.get("site_url", "https://www.amobbs.com").rstrip("/")
            reader = DiscuzForumReader(
                site_url=site_url,
                cookies=self.config.get("cookie", ""),
                username=self.config.get("username", ""),
                password=self.config.get("password", ""),
            )
            detail = reader.get_thread_detail(tid=thread_id)
            if not detail:
                return None
            return Article(
                title="", body=detail.get("content", ""),
                source=self.name,
                source_url=f"{site_url}/forum.php?mod=viewthread&tid={thread_id}",
                source_id=thread_id,
                author=detail.get("author", ""),
                raw=detail,
            )
        except Exception:
            return None

    # ─── 回复评论 ─────────────────────────────
    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """回复指定帖子的评论"""
        if not thread_id or not content:
            return {"supported": True, "success": False, "error": "缺少帖子ID或回复内容"}
        try:
            from plugins.publisher_discuz import DiscuzPublisher
            publisher = DiscuzPublisher(self.config)
            # 使用 Publisher 的 human session 提交回复
            from plugins.browser_session import HumanSession
            site_url = self.config.get("site_url", "https://www.amobbs.com").rstrip("/")
            browser = HumanSession(base_url=site_url, min_delay=0.5, max_delay=2.0)
            cookie = self.config.get("cookie", "")
            if cookie:
                browser.set_cookies(cookie)

            # 1. 访问帖子页面获取 formhash
            thread_url = f"/forum.php?mod=viewthread&tid={thread_id}"
            resp = browser.get(thread_url)

            formhash = None
            for pattern in [r'name="formhash"[^>]+value="([^"]+)"',
                            r'formhash\s*=\s*"([^"]+)"',
                            r'formhash=([a-zA-Z0-9]+)']:
                m = re.search(pattern, resp.text)
                if m:
                    formhash = m.group(1)
                    break

            if not formhash:
                return {"supported": True, "success": False,
                        "error": "无法获取回复表单 formhash，可能 Cookie 已过期"}

            # 2. 提交回复
            time.sleep(random.uniform(0.5, 1.5))

            reply_data = {
                "formhash": formhash,
                "message": content,
                "replysubmit": "true",
            }
            if comment_id:
                reply_data["reppid"] = comment_id

            reply_url = f"/forum.php?mod=post&action=reply&tid={thread_id}&replysubmit=yes"
            resp = browser.post(reply_url, data=reply_data)

            # 3. 判断结果
            if "viewthread" in resp.url and "tid" in resp.url:
                return {"supported": True, "success": True,
                        "url": f"{site_url}/forum.php?mod=viewthread&tid={thread_id}",
                        "message": "回复成功"}
            if "提示信息" in resp.text:
                msg_match = re.search(r'<div[^>]*id="messagetext"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
                msg = re.sub(r"<[^>]+>", " ", msg_match.group(1)).strip()[:200] if msg_match else "未知"
                if "审核" in msg or "等待" in msg:
                    return {"supported": True, "success": True,
                            "url": f"{site_url}/forum.php?mod=viewthread&tid={thread_id}",
                            "error": msg, "message": "回复提交成功，等待审核"}
                return {"supported": True, "success": False, "error": msg}

            err = re.search(r'<div[^>]*class="alert_error"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
            if err:
                return {"supported": True, "success": False,
                        "error": re.sub(r"<[^>]+>", " ", err.group(1)).strip()[:300]}

            return {"supported": True, "success": True, "message": "回复已提交"}
        except Exception as e:
            return {"supported": True, "success": False, "error": f"回复异常: {e}"}

    # ─── 逛论坛 ───────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """浏览论坛板块列表，推荐感兴趣的内容"""
        try:
            from plugins.forum_reader import DiscuzForumReader
            site_url = self.config.get("site_url", "https://www.amobbs.com").rstrip("/")
            reader = DiscuzForumReader(
                site_url=site_url,
                cookies=self.config.get("cookie", ""),
                username=self.config.get("username", ""),
                password=self.config.get("password", ""),
            )
            forums = reader.get_forum_list()
            result = {
                "supported": True,
                "total": len(forums),
                "filtered": 0,
                "new_saved": 0,
                "forums": forums,
            }
            fid = kwargs.get("fid", self.config.get("fid"))
            if fid:
                hours = kwargs.get("hours", 24)
                max_pages = kwargs.get("max_pages", 1)
                threads = reader.get_new_threads(
                    fid=fid, hours=hours, max_pages=max_pages
                )
                result["threads"] = threads
                result["filtered"] = len(threads)
            return result
        except Exception as e:
            return {"supported": True, "total": 0, "filtered": 0, "new_saved": 0,
                    "forums": [], "error": str(e)}

    # ─── 部署 ─────────────────────────────────
    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        """阿莫论坛不涉及站点部署"""
        return {"supported": False}
