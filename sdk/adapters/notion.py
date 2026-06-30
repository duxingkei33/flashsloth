"""
Notion Source Adapter — 从 Notion 数据库采集文章

设计为 SOURCE 适配器，仅实现 fetch_posts() 拉取文章。
实际 Notion API 调用由 provider_*.py 完成，当前为占位实现。
"""
from ..adapter import PlatformAdapter, register, Article, get_db


@register
class NotionAdapter(PlatformAdapter):
    name = "notion"
    display_name = "Notion"
    site_url = "https://www.notion.so"
    version = "1.0.0"
    description = "从 Notion 数据库采集文章内容"
    author = "FlashSloth"
    icon = "📝"

    config_fields = [
        {
            "key": "api_key",
            "label": "Notion API Key",
            "type": "password",
            "required": True,
            "placeholder": "ntn_xxxxxxxxxxxxxxxxxxxx",
            "description": "Notion Integration Token（Internal Integration Secret）",
        },
        {
            "key": "database_id",
            "label": "Database ID",
            "type": "text",
            "required": True,
            "placeholder": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "description": "Notion 数据库 ID（URL 中 32 位 UUID）",
        },
    ]

    def __init__(self, config: dict = None):
        super().__init__(config)
        self.api_key = (config or {}).get("api_key", "")
        self.database_id = (config or {}).get("database_id", "")

    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """
        从 Notion 数据库采集文章。

        当前为占位实现 —— 实际 Notion 采集逻辑由 provider_*.py 完成，
        通过 admin.py 调度。后续可在此集成 Notion API 客户端。
        """
        if not self.api_key or not self.database_id:
            return []

        # TODO: 集成 Notion API 客户端，从数据库查询 page 并转成 Article 列表
        # 参考 https://developers.notion.com/reference/post-database-query
        #
        # 示例流程：
        # 1. POST https://api.notion.com/v1/databases/{database_id}/query
        #    Header: Authorization: Bearer {api_key}
        #    Header: Notion-Version: 2022-06-28
        #    Body: {"filter": {"timestamp": "last_edited_time", ...}}
        # 2. 遍历 results，解析 page properties 和 blocks
        # 3. 每个 page → Article(...)

        return []

    def test_connection(self) -> dict:
        """测试 Notion API 连通性"""
        if not self.api_key:
            return {
                "supported": True,
                "success": False,
                "error": "未配置 Notion API Key",
                "status": "配置不完整",
            }
        if not self.database_id:
            return {
                "supported": True,
                "success": False,
                "error": "未配置 Database ID",
                "status": "配置不完整",
            }
        return {
            "supported": True,
            "success": True,
            "error": "",
            "status": "配置就绪（占位实现，未实际连接）",
        }
