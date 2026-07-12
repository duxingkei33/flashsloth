"""
掘金 (juejin.cn) 平台适配器

能力清单：预留接口，需测试账号
  - publish()             发布文章 ✅（通过 Cookie）
  - fetch_posts()         采集（⏳ 需掘金测试账号）
  - fetch_thread_detail() 读文章详情（⏳ 需掘金测试账号）
  - browse_forum()        逛掘金（⏳ 需掘金测试账号）

注意：掘金使用 Cookie 鉴权，需要测试账号才能完善浏览/采集功能。
"""
from typing import Optional
from ..adapter import PlatformAdapter, register, Article, Comment


@register
class JuejinAdapter(PlatformAdapter):
    name = "juejin"
    display_name = "掘金"
    site_url = "https://juejin.cn"
    icon = "🟠"

    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录掘金后从浏览器 F12 复制 Cookie"},
    ]

    def __init__(self, config=None):
        super().__init__(config)
        self.cookie = (config or {}).get("cookie", "")

    def publish(self, article: Article, **kwargs) -> dict:
        if not self.cookie:
            return {"supported": True, "success": False, "error": "缺少 Cookie"}
        from plugins.publisher_juejin import JuejinPublisher
        return JuejinPublisher(self.config).publish(article)

    def fetch_posts(self, hours=24, max_pages=3, **kwargs) -> list[Article]:
        return []

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        return None

    def browse_forum(self, **kwargs) -> dict:
        return {"supported": True, "total": 0, "message": "⏳ 需要掘金测试账号才能实现浏览功能"}

    def test_connection(self) -> dict:
        if not self.cookie:
            return {"success": False, "error": "Cookie 未配置"}
        return {"success": True, "status": "Cookie 已配置"}
