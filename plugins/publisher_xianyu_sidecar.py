"""
FlashSloth — 闲鱼自动回复 Sidecar 适配器

适配 zhinianboke/xianyu-auto-reply Docker 服务的 REST API，
为 FlashSloth 提供闲鱼商品列表、订单查询、发布等能力。

架构模式：Sidecar 集成（不直接操作闲鱼，通过 xianyu-auto-reply 代理）

依赖：
  - xianyu-auto-reply Docker 服务运行中（http://localhost:8089）
  - 可通过 docker compose -f docker-compose.yml -f docker-compose.flashsloth.yml up -d --build 启动

xianyu-auto-reply API 端点 (FastAPI):
  GET  /items                    — 商品列表
  GET  /items/paginated          — 分页商品列表（支持过滤）
  GET  /items/cookie/{cookie_id} — 按账号查询商品
  GET  /orders                   — 订单列表（支持状态/日期过滤）
  POST /product-publish/materials — 创建商品素材
  GET  /product-publish/materials — 素材库列表
  POST /product-publish/publish  — 发布商品
"""
import json
import logging
from typing import Optional
from urllib.parse import urljoin

import requests

from flashsloth.core.publisher import Publisher, Article, register

logger = logging.getLogger(__name__)

# ====== 配置 ======

XIANYU_AUTO_REPLY_BASE = "http://localhost:8089"
REQUEST_TIMEOUT = 30  # seconds


# ====== Sidecar API 客户端 ======

class XianyuAutoReplyClient:
    """xianyu-auto-reply 后端 API 客户端"""

    def __init__(self, base_url: str = XIANYU_AUTO_REPLY_BASE):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self._token: Optional[str] = None

    def set_token(self, token: str):
        """设置 JWT 认证 Token（从 xianyu-auto-reply 登录获取）"""
        self._token = token
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        try:
            resp = self.session.request(method, url, **kwargs)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"success": True, "data": data}
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ 无法连接 xianyu-auto-reply: {self.base_url}")
            return {"success": False, "error": "服务未运行，请启动 Docker 容器"}
        except requests.exceptions.Timeout:
            logger.error(f"⏰ 请求超时: {url}")
            return {"success": False, "error": "请求超时"}
        except Exception as e:
            logger.error(f"❌ API 请求失败 [{method} {path}]: {e}")
            return {"success": False, "error": str(e)}

    def get(self, path: str, params: dict = None) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, json_data: dict = None) -> dict:
        return self._request("POST", path, json=json_data)

    # ----- 商品接口 -----

    def list_items(self, cookie_id: str = None) -> list:
        """获取商品列表"""
        if cookie_id:
            result = self.get(f"/items/cookie/{cookie_id}")
            return result.get("items", [])
        result = self.get("/items")
        return result.get("items", [])

    def list_items_paginated(
        self,
        cookie_id: str = None,
        page: int = 1,
        page_size: int = 20,
        keyword: str = None,
    ) -> dict:
        """分页查询商品"""
        params = {"page": page, "page_size": page_size}
        if cookie_id:
            params["cookie_id"] = cookie_id
        if keyword:
            params["keyword"] = keyword
        result = self.get("/items/paginated", params=params)
        return result

    # ----- 订单接口 -----

    def list_orders(
        self,
        cookie_id: str = None,
        status: str = None,
        page: int = 1,
        page_size: int = 20,
        start_date: str = None,
        end_date: str = None,
    ) -> dict:
        """查询订单列表"""
        params = {"page": page, "page_size": page_size}
        if cookie_id:
            params["cookie_id"] = cookie_id
        if status:
            params["status"] = status
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self.get("/orders", params=params)

    # ----- 商品素材接口 -----

    def create_material(self, data: dict) -> dict:
        """创建商品素材（发布模板）"""
        return self.post("/product-publish/materials", json_data=data)

    def list_materials(self, page: int = 1, page_size: int = 20) -> dict:
        """获取素材库列表"""
        return self.get("/product-publish/materials", params={"page": page, "page_size": page_size})

    def publish_product(self, material_id: int, account_ids: list) -> dict:
        """发布商品（触发 Playwright 自动化）"""
        return self.post("/product-publish/publish", json_data={
            "material_id": material_id,
            "cookie_ids": account_ids,
        })

    # ----- 状态检查 -----

    def health_check(self) -> dict:
        """检查 xianyu-auto-reply 服务健康状态"""
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            if resp.status_code == 200:
                return {"success": True, "status": resp.json()}
            return {"success": False, "status": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "status": str(e)}


# ====== FlashSloth Publisher 适配 ======

@register
class XianyuSidecarPublisher(Publisher):
    """闲鱼 Sidecar 发布器 — 通过 xianyu-auto-reply 代理操作"""
    name = "xianyu_sidecar"
    display_name = "闲鱼(自动回复)"
    description = "闲鱼自动回复 Sidecar — 包装 zhinianboke/xianyu-auto-reply Docker 服务的 REST API"
    icon = "🐟"
    supports_draft = False  # 闲鱼无草稿功能
    capabilities = ["publish_product", "list_products", "query_orders"]

    login_methods = [
        {"method": "password", "label": "淘宝账号密码登录", "icon": "🔑", "priority": 1,
         "fields": ["site_url", "username", "password"],
         "description": "输入淘宝账号密码，xianyu-auto-reply 自动处理登录"},
        {"method": "cookie", "label": "Cookie 登录（备选）", "icon": "🍪", "priority": 99,
         "fields": ["site_url", "cookie"],
         "description": "从浏览器 F12 复制闲鱼 Cookie"},
    ]

    config_fields = [
        {"key": "site_url", "label": "闲鱼地址", "type": "text", "required": False,
         "default": "https://goofish.com"},
        {"key": "api_base", "label": "Sidecar API 地址", "type": "text", "required": False,
         "default": XIANYU_AUTO_REPLY_BASE,
         "description": "xianyu-auto-reply 后端服务地址（Docker 容器内网地址或宿主机 localhost）"},
        {"key": "api_token", "label": "API Token（可选）", "type": "password", "required": False,
         "default": "",
         "description": "xianyu-auto-reply 登录后的 JWT Token"},
        {"key": "username", "label": "淘宝账号（手机号/邮箱）", "type": "text", "required": False, "default": ""},
        {"key": "password", "label": "淘宝密码", "type": "password", "required": False, "default": ""},
        {"key": "cookie", "label": "Cookie（备选）", "type": "textarea", "required": False,
         "placeholder": "从浏览器复制的完整 Cookie"},
    ]

    def __init__(self, config: dict = None):
        super().__init__(config or {})
        api_base = self.config.get("api_base", XIANYU_AUTO_REPLY_BASE)
        self._client = XianyuAutoReplyClient(api_base)
        token = self.config.get("api_token", "")
        if token:
            self._client.set_token(token)

    @classmethod
    def get_login_methods(cls) -> list[dict]:
        return sorted(cls.login_methods, key=lambda m: m.get("priority", 99))

    def check_connection(self) -> dict:
        """检查 xianyu-auto-reply 服务连通性"""
        result = self._client.health_check()
        if result.get("success"):
            return {"success": True, "error": ""}
        return {"success": False, "error": result.get("status", "服务不可达")}

    def list_products(self, page: int = 1, page_size: int = 20, account_id: str = None) -> list:
        """列出闲鱼商品（通过 Sidecar 代理）"""
        result = self._client.list_items_paginated(
            cookie_id=account_id,
            page=page,
            page_size=page_size,
        )
        items = result.get("data", []) if isinstance(result, dict) else []
        return items

    def query_orders(
        self,
        account_id: str = None,
        status: str = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """查询闲鱼订单（通过 Sidecar 代理）"""
        return self._client.list_orders(
            cookie_id=account_id,
            status=status,
            page=page,
            page_size=page_size,
        )

    def publish(self, article: Article, **kwargs) -> dict:
        """发布商品到闲鱼（通过 xianyu-auto-reply 代理）

        注意：闲鱼无草稿功能，每次调用直接发布。
        依赖：xianyu-auto-reply Docker 服务必须运行。
        """
        # 先创建素材
        material_data = {
            "title": article.title,
            "description": article.body,
            "price": float(kwargs.get("price", 0)),
            "original_price": kwargs.get("original_price"),
            "category": kwargs.get("category", ""),
            "images": article.images or [],
            "delivery_method": kwargs.get("delivery_method", "express"),
            "postage": float(kwargs.get("postage", 0)),
            "address": kwargs.get("address", ""),
            "condition": kwargs.get("condition", "全新"),
        }
        material_result = self._client.create_material(material_data)
        if not material_result.get("success", True):
            return {"success": False, "error": material_result.get("error", "创建素材失败")}

        material_id = material_result.get("id") or material_result.get("data", {}).get("id")
        if not material_id:
            return {"success": False, "error": "素材创建后未返回ID"}

        # 发布
        account_ids = kwargs.get("account_ids", [])
        return self._client.publish_product(material_id, account_ids)

    def get_product_info(self, item_id: str) -> dict:
        """获取单个商品详情（通过 Sidecar 代理）"""
        result = self._client.list_items_paginated(keyword=item_id, page=1, page_size=1)
        items = result.get("data", [])
        if items:
            return {"success": True, "data": items[0]}
        return {"success": False, "error": f"未找到商品 {item_id}"}


# ====== 便利函数 ======

def get_sidecar_status() -> dict:
    """获取 xianyu-auto-reply 服务状态"""
    client = XianyuAutoReplyClient()
    return client.health_check()


def launch_docker_command() -> str:
    """返回启动 xianyu-auto-reply Docker 的命令"""
    return (
        "cd ~/.hermes/flashsloth/xianyu-auto-reply && "
        "docker compose -f docker-compose.yml -f docker-compose.flashsloth.yml up -d --build"
    )
