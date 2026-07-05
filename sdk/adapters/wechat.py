"""
微信公众号 (mp.weixin.qq.com) 平台适配器

能力清单：预留接口，需测试账号
  - publish()             发布文章 ✅（通过 Selenium 浏览器自动化）
  - fetch_posts()         采集（⏳ 需公众号测试账号）
  - browse_forum()        浏览（⏳ 需公众号测试账号）

注意：微信公众号平台需要绑定运营者微信，登录方式特殊（扫码），
需要测试账号才能完善浏览/采集功能。
"""
from typing import Optional
from ..adapter import PlatformAdapter, register, Article, Comment


@register
class WeChatAdapter(PlatformAdapter):
    name = "wechat"
    display_name = "微信公众号"
    site_url = "https://mp.weixin.qq.com"
    icon = "💚"

    config_fields = [
        {"key": "username", "label": "邮箱", "type": "text", "required": True,
         "placeholder": "公众号登录邮箱"},
        {"key": "password", "label": "密码", "type": "password", "required": True,
         "placeholder": "公众号登录密码"},
    ]

    def __init__(self, config=None):
        super().__init__(config)

    def publish(self, article: Article, **kwargs) -> dict:
        from plugins.publisher_wechat import WeChatPublisher
        return WeChatPublisher(self.config).publish(article)

    def fetch_posts(self, hours=24, max_pages=3, **kwargs) -> list[Article]:
        return []

    def browse_forum(self, **kwargs) -> dict:
        return {"supported": True, "total": 0, "message": "⏳ 需要公众号测试账号才能实现浏览功能"}

    def test_connection(self) -> dict:
        return {"supported": True, "success": True, "status": "已配置"}
