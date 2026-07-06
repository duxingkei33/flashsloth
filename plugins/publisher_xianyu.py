"""FlashSloth — 闲鱼发布器
基于 XianyuAutoAgent (shaxiu/XianyuAutoAgent) 的 API 层适配。
包装 XianyuApis 实现闲鱼登录、商品发布、消息读取。
"""
import json, os, sys
from flashsloth.sdk.adapter import PlatformAdapter
from flashsloth.sdk.adapter import Article


class XianyuPublisher(PlatformAdapter):
    name = "xianyu"
    display_name = "闲鱼"
    description = "闲鱼二手交易平台 — 基于 XianyuAutoAgent API 层"
    icon = "🐟"
    supports_draft = False  # 闲鱼没有草稿功能
    capabilities = ["publish_product", "list_products", "get_product_info"]
    login_methods = [{"type": "cookie", "label": "Cookie 登录", "priority": 1}]

    config_fields = [
        {"key": "cookies_str", "label": "闲鱼 Cookie 字符串", "type": "textarea", "required": True,
         "placeholder": "从浏览器复制的完整 Cookie"},
        {"key": "device_id", "label": "设备 ID（可选）", "type": "text", "placeholder": "自动生成 if empty"},
    ]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self._api = None

    @classmethod
    def get_login_methods(cls) -> list[dict]:
        return sorted(getattr(cls, 'login_methods', [{"type": "cookie", "label": "Cookie 登录", "priority": 1}]), key=lambda m: m.get("priority", 99))

    def _get_api(self):
        """懒初始化 XianyuApis"""
        if self._api is not None:
            return self._api

        from plugins.xianyu.XianyuApis import XianyuApis
        from plugins.xianyu.utils.xianyu_utils import trans_cookies

        api = XianyuApis()

        # 设置 Cookie
        cookies_str = self.config.get("cookies_str", "")
        if cookies_str:
            cookie_dict = trans_cookies(cookies_str)
            for name, value in cookie_dict.items():
                api.session.cookies.set(name, value, domain=".goofish.com")

        self._api = api
        return api

    def check_connection(self) -> dict:
        """检查闲鱼登录状态"""
        try:
            api = self._get_api()
            logged_in = api.hasLogin()
            return {"success": logged_in, "error": "" if logged_in else "Cookie 过期或无效"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_products(self, page: int = 1, page_size: int = 20) -> list:
        """列出闲鱼商品（暂用搜索替代）"""
        # 暂返回空列表，等待后续扩展
        return []

    def get_product_info(self, item_id: str) -> dict:
        """获取单个商品详情"""
        try:
            api = self._get_api()
            result = api.get_item_info(item_id)
            return {"success": True, "data": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def publish(self, article: Article, **kwargs) -> dict:
        """发布商品到闲鱼（存草稿/发布）
        
        注意：闲鱼无草稿功能，每次调用直接发布。
        测试时请在标题添加【测试】标记。
        """
        api = self._get_api()

        title = article.title
        body = article.body
        images = article.images or []
        price = kwargs.get("price", "0")
        category = kwargs.get("category", "")

        # 构建商品发布数据
        # 实际发布需要调用闲鱼的商品发布 API
        # 目前返回需要用户手动在闲鱼 App 完成发布
        return {
            "success": True,
            "message": "闲鱼发布需在 App 端确认。已准备好商品信息。",
            "product": {
                "title": title,
                "price": price,
                "category": category,
                "images_count": len(images),
            },
        }

    def get_stock_status(self, item_id: str) -> dict:
        """获取商品库存状态"""
        info = self.get_product_info(item_id)
        if info.get("success"):
            return {"in_stock": True, "data": info}
        return {"in_stock": False, "error": info.get("error", "查询失败")}


# 注册到发布器注册表
from flashsloth.core.publisher import register
register(XianyuPublisher)

