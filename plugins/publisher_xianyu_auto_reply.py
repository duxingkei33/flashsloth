"""
闲鱼自动回复系统 (xianyu-auto-reply) 集成插件

将 zhinianboke/xianyu-auto-reply Docker 服务集成到 FlashSloth 后台，
提供统一的管理入口和 API 代理。

功能:
  1. 在 FlashSloth 导航栏添加闲鱼管理入口
  2. 在账号管理页面添加 xianyu-auto-reply 后台链接
  3. 代理 xianyu-auto-reply 的 API（商品发布/订单查询）

依赖:
  - xianyu-auto-reply 服务需已通过 Docker 部署运行
  - 默认后端地址: http://localhost:8089
  - 默认前端地址: http://localhost:9000
"""

import os
import json
import requests
from typing import Optional

from flashsloth.core.publisher import Publisher, register, PublishError


# 默认 xianyu-auto-reply 服务地址
DEFAULT_BACKEND_URL = os.environ.get("XY_AUTO_REPLY_URL", "http://localhost:8089")
DEFAULT_FRONTEND_URL = os.environ.get("XY_AUTO_REPLY_FRONTEND", "http://localhost:9000")


@register
class XianyuAutoReplyPublisher(Publisher):
    """
    闲鱼自动回复系统 Publisher

    对接 xianyu-auto-reply 的 REST API，通过 FlashSloth 账号配置中的 Cookie
    调用其商品发布和订单查询接口。
    """

    name = "xianyu_auto_reply"
    display_name = "闲鱼自动回复 (Docker)"
    architecture = "闲鱼平台"
    login_methods = [
        {
            "method": "cookie",
            "label": "Cookie 导入",
            "icon": "🍪",
            "priority": 1,
            "fields": ["cookie"],
            "description": "导入闲鱼 Cookie（从 xianyu-auto-reply 后台复制）",
        },
    ]
    config_fields = [
        {
            "key": "backend_url",
            "label": "后端地址",
            "type": "text",
            "required": False,
            "default": DEFAULT_BACKEND_URL,
            "placeholder": "http://localhost:8089",
        },
        {
            "key": "cookie",
            "label": "闲鱼 Cookie",
            "type": "password",
            "required": True,
            "placeholder": "闲鱼登录 Cookie",
        },
        {
            "key": "admin_username",
            "label": "后台用户名",
            "type": "text",
            "required": False,
            "placeholder": "xianyu-auto-reply 管理员账号",
        },
        {
            "key": "admin_password",
            "label": "后台密码",
            "type": "password",
            "required": False,
            "placeholder": "xianyu-auto-reply 管理员密码",
        },
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.backend_url = (config or {}).get("backend_url", DEFAULT_BACKEND_URL)
        self.cookie = (config or {}).get("cookie", "")
        self.admin_username = (config or {}).get("admin_username", "")
        self.admin_password = (config or {}).get("admin_password", "")
        self._session = requests.Session()

    # ─── 管理后台链接 ─────────────────────────────

    def get_admin_urls(self) -> list[dict]:
        """返回 xianyu-auto-reply 管理后台链接列表"""
        frontend = self.config.get("frontend_url", DEFAULT_FRONTEND_URL) if hasattr(self, 'config') and isinstance(self.config, dict) else DEFAULT_FRONTEND_URL
        return [
            {
                "name": "闲鱼后台 (前端)",
                "url": frontend,
                "icon": "🖥️",
                "description": "xianyu-auto-reply 管理页面",
            },
            {
                "name": "后端 API",
                "url": f"{self.backend_url}/docs",
                "icon": "📡",
                "description": "xianyu-auto-reply API 文档 (Swagger)",
            },
            {
                "name": "健康检查",
                "url": f"{self.backend_url}/health",
                "icon": "💚",
                "description": "服务健康状态",
            },
        ]

    # ─── 商品发布 ─────────────────────────────

    def publish(self, article, **kwargs) -> dict:
        """
        通过 xianyu-auto-reply API 发布商品。

        Article 字段映射:
            title    → 商品标题
            body     → 商品描述
            images   → 商品图片

        kwargs:
            price       — 价格（必填）
            condition   — 成色
            category_id — 分类 ID
            location    — 所在地
        """
        if not self._check_health():
            return {
                "success": False, "url": "", "id": "",
                "error": "xianyu-auto-reply 服务未运行",
            }

        title = article.title.strip() if article.title else ""
        if not title:
            return {"success": False, "url": "", "id": "", "error": "标题不能为空"}

        price = kwargs.get("price", "")
        if not price:
            return {"success": False, "url": "", "id": "", "error": "价格不能为空"}

        # 调用 xianyu-auto-reply API 发布商品
        payload = {
            "title": title[:30],
            "description": (article.body or "")[:500],
            "price": str(price),
            "images": article.images or kwargs.get("images", []),
            "condition": kwargs.get("condition", "slight_use"),
            "category_id": kwargs.get("category_id", ""),
            "location": kwargs.get("location", ""),
            "quantity": kwargs.get("quantity", 1),
        }

        try:
            resp = self._session.post(
                f"{self.backend_url}/api/v1/products",
                json=payload,
                headers={"Cookie": self.cookie} if self.cookie else {},
                timeout=30,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return {
                    "success": True,
                    "url": data.get("url", ""),
                    "id": str(data.get("id", "")),
                    "error": "",
                    "message": f"商品发布成功: {title}",
                }
            return {
                "success": False, "url": "", "id": "",
                "error": f"发布失败: {resp.status_code} {resp.text[:200]}",
            }
        except requests.exceptions.ConnectionError:
            return {"success": False, "url": "", "id": "", "error": "无法连接 xianyu-auto-reply"}
        except Exception as e:
            return {"success": False, "url": "", "id": "", "error": str(e)}

    # ─── 订单查询 ─────────────────────────────

    def query_orders(self, status: str = "all", page: int = 1, page_size: int = 20) -> dict:
        """
        查询闲鱼订单列表。

        参数:
            status:    all | pending | shipped | completed | refund
            page:      页码
            page_size: 每页数量

        返回:
            supported: bool
            success:   bool
            orders:    list[dict]
            total:     int
            error:     str
        """
        if not self._check_health():
            return {"supported": True, "success": False, "orders": [], "total": 0,
                    "error": "xianyu-auto-reply 服务未运行"}

        try:
            params = {"page": page, "page_size": page_size}
            if status != "all":
                params["status"] = status

            resp = self._session.get(
                f"{self.backend_url}/api/v1/orders",
                params=params,
                headers={"Cookie": self.cookie} if self.cookie else {},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "supported": True,
                    "success": True,
                    "orders": data.get("orders", data.get("items", [])),
                    "total": data.get("total", 0),
                    "error": "",
                }
            return {
                "supported": True, "success": False, "orders": [], "total": 0,
                "error": f"查询失败: {resp.status_code}",
            }
        except requests.exceptions.ConnectionError:
            return {"supported": True, "success": False, "orders": [], "total": 0,
                    "error": "无法连接 xianyu-auto-reply"}
        except Exception as e:
            return {"supported": True, "success": False, "orders": [], "total": 0,
                    "error": str(e)}

    # ─── 平台信息 ─────────────────────────────

    def get_info(self):
        from flashsloth.sdk import PlatformInfo
        return PlatformInfo(
            name=self.name,
            display_name=self.display_name,
            site_url=self.backend_url,
            version="1.0.0",
            description="基于 zhinianboke/xianyu-auto-reply Docker 的闲鱼自动回复系统",
        )

    # ─── 工具方法 ─────────────────────────────

    def _check_health(self) -> bool:
        """检查 xianyu-auto-reply 服务是否运行"""
        try:
            resp = self._session.get(
                f"{self.backend_url}/health", timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False

    def test_connection(self) -> dict:
        """测试连接"""
        if self._check_health():
            return {"success": True, "error": "", "status": "已连接"}
        return {
            "success": False,
            "error": f"无法连接到 {self.backend_url}",
            "status": "未连接",
        }


# ─── 辅助函数：获取 Admin 入口链接 ─────────────────

def get_xianyu_admin_links() -> list[dict]:
    """获取所有 xianyu-auto-reply 管理链接（供 routes 调用）"""
    return [
        {
            "name": "闲鱼自动回复后台",
            "url": DEFAULT_FRONTEND_URL,
            "icon": "🖥️",
            "description": "xianyu-auto-reply 管理面板（商品、订单、账号）",
        },
        {
            "name": "闲鱼 API 文档",
            "url": f"{DEFAULT_BACKEND_URL}/docs",
            "icon": "📡",
            "description": "xianyu-auto-reply Swagger API 文档",
        },
        {
            "name": "闲鱼健康检查",
            "url": f"{DEFAULT_BACKEND_URL}/health",
            "icon": "💚",
            "description": "服务健康状态",
        },
    ]
