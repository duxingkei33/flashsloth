"""
阿莫论坛 (amobbs.com) 平台适配器

基于 Discuz! 引擎，复用 DiscuzPublisher 发帖、DiscuzForumReader 采集。

能力清单：
  - sign_in()             签到（不支持）
  - publish()             发布帖子 ✅
  - retract()             撤回（不支持）
  - fetch_posts()         采集新帖 ✅
  - fetch_replies()       采集回复（不支持）
  - fetch_thread_detail() 读帖详情 ✅
  - reply_comment()       回复评论（不支持）
  - browse_forum()        逛论坛（不支持）
  - deploy()              部署（不支持）
"""
from typing import Optional

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
        """阿莫论坛暂不支持批量采集回复"""
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
        """阿莫论坛暂不支持自动回复评论"""
        return {"supported": False}

    # ─── 逛论坛 ───────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """阿莫论坛暂不支持自动逛论坛"""
        return {"supported": False}

    # ─── 部署 ─────────────────────────────────
    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        """阿莫论坛不涉及站点部署"""
        return {"supported": False}
