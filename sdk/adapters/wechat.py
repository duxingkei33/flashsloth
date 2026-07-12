"""
微信公众号 (mp.weixin.qq.com) 平台适配器

能力：
  - publish()            发布文章（通过官方 API 存草稿）
  - test_connection()    验证 AppID+AppSecret 有效性
  - fetch_posts()        采集（⏳ 需测试账号）
  - browse_forum()       浏览（⏳ 需测试账号）

注意：微信公众号平台需要 AppID + AppSecret 才能使用官方 API。
浏览器方式需要绑定运营者微信并扫码登录。
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
        {"key": "app_id", "label": "AppID", "type": "text", "required": True,
         "placeholder": "从公众号后台获取"},
        {"key": "app_secret", "label": "AppSecret", "type": "password", "required": True,
         "placeholder": "从公众号后台获取"},
    ]

    def __init__(self, config=None):
        super().__init__(config)

    def publish(self, article: Article, **kwargs) -> dict:
        from plugins.publisher_wechat import WeChatPublisher
        return WeChatPublisher(self.config).publish(article)

    def test_connection(self) -> dict:
        from plugins.publisher_wechat import WeChatPublisher
        return WeChatPublisher(self.config).test_connection()

    def fetch_posts(self, hours=24, max_pages=3, **kwargs) -> list[Article]:
        return []

    def browse_forum(self, **kwargs) -> dict:
        return {"supported": True, "total": 0,
                "message": "⏳ 需要公众号测试账号才能实现浏览/采集功能"}
