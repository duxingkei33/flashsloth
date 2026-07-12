"""TaobaoProvider — 淘宝商品数据采集框架（预留）"""
import os
from typing import Optional

from flashsloth.core.provider import Provider, ContentItem, register_provider


@register_provider
class TaobaoProvider(Provider):
    name = "taobao"
    display_name = "淘宝商品"
    description = "淘宝商品数据采集（预留，需要淘宝账号 Cookie）"
    icon = "🛒"
    config_fields = [
        {"key": "cookie", "label": "淘宝 Cookie", "type": "password", "default": "", "hint": "淘宝登录后的 Cookie 字符串", "required": True},
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self._cookie = (config or {}).get("cookie", "")

    def list_items(self) -> list[ContentItem]:
        """（预留）淘宝商品列表"""
        return []

    def get_item(self, item_id: str) -> Optional[ContentItem]:
        """（预留）获取单个商品"""
        return None

    def get_item_content(self, item_id: str) -> str:
        """（预留）获取商品详情"""
        return ""

    def validate_config(self) -> list[str]:
        """验证配置"""
        missing = []
        if not self._cookie:
            missing.append("cookie (淘宝 Cookie)")
        return missing
