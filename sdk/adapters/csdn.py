"""
CSDN 平台适配器
继承 PlatformAdapter，注册为 'csdn'
"""
from ..adapter import PlatformAdapter, register, Article, get_db
import json


@register
class CSDNAdapter(PlatformAdapter):
    name = "csdn"
    display_name = "CSDN"
    site_url = "https://blog.csdn.net"
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录 CSDN 后从浏览器复制"},
    ]

    def __init__(self, config=None):
        super().__init__(config)
        self.cookie = (config or {}).get("cookie", "")

    def publish(self, article: Article, **kwargs) -> dict:
        if not self.cookie:
            return {"supported": True, "success": False, "error": "缺少 Cookie"}
        try:
            from plugins.publisher_csdn import CSDNPublisher
            pub = CSDNPublisher(self.config)
            return pub.publish(article)
        except Exception as e:
            return {"supported": True, "success": False, "error": str(e)}

    def test_connection(self) -> dict:
        if not self.cookie:
            return {"supported": True, "success": False, "error": "Cookie 未配置"}
        return {"supported": True, "success": True, "status": "Cookie 已配置"}
