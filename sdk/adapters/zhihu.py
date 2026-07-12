"""
知乎 (zhihu.com) 平台适配器

能力清单：预留接口，需测试账号
  - publish()             发布文章 ✅（通过 Cookie）
  - fetch_posts()         采集（⏳ 需知乎测试账号）
  - fetch_thread_detail() 读文章详情（⏳ 需知乎测试账号）
  - browse_forum()        逛知乎（⏳ 需知乎测试账号）

注意：知乎有强反爬 + 登录 SSO（微信/手机），需要测试账号才能完善。
"""
from typing import Optional
from ..adapter import PlatformAdapter, register, Article, Comment


@register
class ZhihuAdapter(PlatformAdapter):
    name = "zhihu"
    display_name = "知乎"
    site_url = "https://www.zhihu.com"
    icon = "🔵"

    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录知乎后从浏览器 F12 复制 Cookie"},
    ]

    def __init__(self, config=None):
        super().__init__(config)
        self.cookie = (config or {}).get("cookie", "")

    def sign_in(self, check_only: bool = False) -> dict:
        return {"supported": False}

    def publish(self, article: Article, **kwargs) -> dict:
        """通过 Cookie 发布文章到知乎"""
        if not self.cookie:
            return {"supported": True, "success": False, "error": "缺少 Cookie"}
        from plugins.publisher_zhihu import ZhihuPublisher
        return ZhihuPublisher(self.config).publish(article)

    def fetch_posts(self, hours=24, max_pages=3, **kwargs) -> list[Article]:
        return []

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        return None

    def browse_forum(self, **kwargs) -> dict:
        return {"supported": True, "total": 0, "message": "⏳ 需要知乎测试账号才能实现浏览功能"}

    def test_connection(self) -> dict:
        if not self.cookie:
            return {"success": False, "error": "Cookie 未配置"}
        return {"success": True, "status": "Cookie 已配置"}
