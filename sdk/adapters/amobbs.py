"""
阿莫论坛 (amobbs.com) 平台适配器

基于 Discuz! 引擎，复用 DiscuzPublisher 发帖、DiscuzForumReader 采集。
"""
from ..adapter import PlatformAdapter, register, Article
from plugins.publisher_discuz import DiscuzPublisher
from plugins.forum_reader import DiscuzForumReader


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
        # 确保 site_url 有默认值
        if not self.config.get("site_url"):
            self.config["site_url"] = "https://www.amobbs.com"

    # ─── 签到 ─────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """阿莫论坛不支持自动签到"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────
    def publish(self, article: Article, **kwargs) -> dict:
        """
        发布帖子到阿莫论坛。

        使用 DiscuzPublisher 的 cookie 模式发帖。
        需先配置 site_url、cookie 和 fid。
        """
        publisher = DiscuzPublisher(self.config)
        return publisher.publish(article, **kwargs)

    # ─── 采集帖子 ─────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """
        从阿莫论坛采集新帖子。

        使用 DiscuzForumReader 抓取指定版块 (fid) 的新帖，
        再获取每篇帖子的详细内容组装为 Article。
        """
        site_url = self.config.get("site_url", "https://www.amobbs.com").rstrip("/")
        cookie = self.config.get("cookie", "")
        username = self.config.get("username", "")
        password = self.config.get("password", "")

        reader = DiscuzForumReader(
            site_url=site_url,
            cookies=cookie,
            username=username,
            password=password,
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
