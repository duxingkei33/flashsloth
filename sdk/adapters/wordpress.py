"""
WordPress (wordpress.org) 平台适配器

能力清单：预留接口，需测试账号
  - publish()             发布文章 ✅（通过 REST API + 应用密码）
  - fetch_posts()         采集（⏳ 需 WordPress 测试站点）
  - fetch_thread_detail() 读文章详情（⏳ 需 WordPress 测试站点）
  - browse_forum()        浏览（⏳ 需 WordPress 测试站点）

注意：WordPress 使用 REST API + 应用密码认证，不需要浏览器登录。
浏览/采集功能需要指定一个具体的站点 URL 才能实现。
"""
from typing import Optional
from ..adapter import PlatformAdapter, register, Article, Comment


@register
class WordPressAdapter(PlatformAdapter):
    name = "wordpress"
    display_name = "WordPress"
    site_url = ""
    icon = "📝"

    config_fields = [
        {"key": "site_url", "label": "站点 URL", "type": "text", "required": True,
         "placeholder": "https://yourblog.com"},
        {"key": "username", "label": "用户名", "type": "text", "required": True,
         "placeholder": "WordPress 用户名"},
        {"key": "app_password", "label": "应用密码", "type": "password", "required": True,
         "placeholder": "WordPress 后台生成的应用密码"},
    ]

    def __init__(self, config=None):
        super().__init__(config)

    def publish(self, article: Article, **kwargs) -> dict:
        from plugins.publisher_wordpress import WordPressPublisher
        return WordPressPublisher(self.config).publish(article)

    def fetch_posts(self, hours=24, max_pages=3, **kwargs) -> list[Article]:
        return []

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        return None

    def browse_forum(self, **kwargs) -> dict:
        return {"supported": True, "total": 0, "message": "⏳ 需要指定 WordPress 站点 URL 才能实现浏览功能"}

    def test_connection(self) -> dict:
        return {"supported": True, "success": True, "status": "已配置"}
