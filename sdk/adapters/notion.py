"""
Notion 平台适配器

从 Notion 数据库采集文章（内容源）。发布功能未来可扩展。

能力清单：
  - sign_in()             签到（不支持，Notion 无签到功能）
  - publish()             发布（不支持，Notion 需手动操作）
  - retract()             撤回（不支持）
  - fetch_posts()         采集数据库文章（TODO: 实际 API 集成）
  - fetch_replies()       采集回复（不支持）
  - fetch_thread_detail() 读帖详情（不支持）
  - reply_comment()       回复评论（不支持）
  - browse_forum()        逛论坛（不支持）
  - deploy()              部署（不支持）
"""
from typing import Optional
from ..adapter import PlatformAdapter, register, Article, Comment


@register
class NotionAdapter(PlatformAdapter):
    name = "notion"
    display_name = "Notion"
    site_url = "https://www.notion.so"
    version = "1.0.0"
    description = "从 Notion 数据库采集文章内容，未来可扩展为发布目标"
    author = "FlashSloth"
    icon = "📝"

    config_fields = [
        {
            "key": "api_key",
            "label": "Notion API Key",
            "type": "password",
            "required": True,
            "placeholder": "ntn_xxxxxxxxxxxxxxxxxxxx",
        },
        {
            "key": "database_id",
            "label": "Database ID",
            "type": "text",
            "required": True,
            "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        },
    ]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_key = (config or {}).get("api_key", "")
        self.database_id = (config or {}).get("database_id", "")

    # ─── 签到 ─────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """Notion 无签到功能"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────
    def publish(self, article: Article, **kwargs) -> dict:
        """Notion 暂不支持作为发布目标（未来可集成 Notion API 创建 Page）"""
        return {"supported": False}

    # ─── 撤回 ─────────────────────────────────
    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """Notion 暂不支持撤回操作"""
        return {"supported": False}

    # ─── 采集帖子 ─────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """
        从 Notion 数据库采集文章。

        当前为占位实现 —— 实际 Notion 采集逻辑由 provider_*.py 完成，
        后续可在此集成 Notion API 客户端。
        """
        if not self.api_key or not self.database_id:
            return []
        # TODO: 集成 Notion API 客户端
        return []

    # ─── 采集回复 ─────────────────────────────
    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """Notion 非论坛/评论平台，不支持采集回复"""
        return []

    # ─── 读帖详情 ─────────────────────────────
    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """Notion 暂不支持按 ID 获取 Page 详细内容（TODO）"""
        return None

    # ─── 回复评论 ─────────────────────────────
    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """Notion 暂不支持自动回复"""
        return {"supported": False}

    # ─── 逛论坛 ───────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """Notion 非论坛，不支持逛论坛"""
        return {"supported": False}

    # ─── 部署 ─────────────────────────────────
    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        """Notion 不涉及站点部署"""
        return {"supported": False}

    # ─── 测试连接 ─────────────────────────────
    def test_connection(self) -> dict:
        if not self.api_key:
            return {"supported": True, "success": False, "error": "未配置 Notion API Key", "status": "配置不完整"}
        if not self.database_id:
            return {"supported": True, "success": False, "error": "未配置 Database ID", "status": "配置不完整"}
        return {"supported": True, "success": True, "error": "", "status": "配置就绪（占位实现，未实际连接）"}
