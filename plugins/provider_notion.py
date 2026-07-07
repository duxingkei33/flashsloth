"""NotionProvider — 从 Notion 数据库读取内容"""
import json
import os
from datetime import datetime
from typing import Optional

from flashsloth.core.provider import Provider, ContentItem, register_provider


@register_provider
class NotionProvider(Provider):
    name = "notion"
    display_name = "Notion 数据库"
    description = "从 Notion 数据库读取文章内容"
    icon = "📄"
    config_fields = [
        {"key": "token", "label": "Notion Token", "type": "password", "default": "", "hint": "Notion API 集成 Token", "required": True},
        {"key": "database_id", "label": "数据库 ID", "type": "text", "default": "", "hint": "Notion 数据库的 32 位 ID", "required": True},
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self._token = (config or {}).get("token", "")
        self._database_id = (config or {}).get("database_id", "")

    def _get_client(self):
        """延迟导入 notion client，避免未安装时崩溃"""
        try:
            from contenthub.provider_notion import NotionClient
            return NotionClient(token=self._token)
        except ImportError:
            pass
        try:
            from contenthub.provider_notion import get_notion_client
            return get_notion_client(token=self._token)
        except ImportError:
            pass
        # fallback: 尝试直接 requests
        return None

    def list_items(self) -> list[ContentItem]:
        """查询 Notion 数据库，返回内容列表"""
        if not self._token or not self._database_id:
            return []

        items = []
        try:
            import requests
            url = f"https://api.notion.com/v1/databases/{self._database_id}/query"
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            }
            resp = requests.post(url, headers=headers, json={}, timeout=30)
            if not resp.ok:
                return []

            data = resp.json()
            for row in data.get("results", []):
                props = row.get("properties", {})
                pid = row["id"]

                # 提取 title
                title = ""
                title_prop = props.get("标题") or props.get("title") or props.get("Name") or {}
                title_list = title_prop.get("title", [])
                if title_list:
                    title = "".join(t.get("plain_text", "") for t in title_list)

                # 提取摘要
                summary = ""
                summary_prop = props.get("摘要") or props.get("summary") or {}
                rich_text_list = summary_prop.get("rich_text", [])
                if rich_text_list:
                    summary = "".join(t.get("plain_text", "") for t in rich_text_list)

                # 提取标签
                tags = []
                tags_prop = props.get("标签") or props.get("tags") or props.get("Tags") or {}
                multi_select = tags_prop.get("multi_select", [])
                if multi_select:
                    tags = [t.get("name", "") for t in multi_select if t.get("name")]

                # 提取创建时间
                created_at = row.get("created_time", "")

                items.append(ContentItem(
                    id=pid,
                    title=title or "(无标题)",
                    summary=summary,
                    source="notion",
                    url=f"https://notion.so/{pid.replace('-', '')}",
                    tags=tags,
                    created_at=created_at,
                    raw_data=row,
                ))
        except Exception:
            return items

        return items

    def get_item(self, item_id: str) -> Optional[ContentItem]:
        """获取单个 Notion 页面元数据"""
        for item in self.list_items():
            if item.id == item_id:
                return item
        return None

    def get_item_content(self, item_id: str) -> str:
        """从 Notion API 获取页面正文（转换为 Markdown）"""
        if not self._token:
            return ""

        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Notion-Version": "2022-06-28",
            }
            # 获取 page 的 blocks
            url = f"https://api.notion.com/v1/blocks/{item_id}/children"
            resp = requests.get(url, headers=headers, timeout=30)
            if not resp.ok:
                return ""

            data = resp.json()
            return self._blocks_to_markdown(data.get("results", []))
        except Exception:
            return ""

    def _blocks_to_markdown(self, blocks: list) -> str:
        """将 Notion blocks 转换为 Markdown 文本"""
        md_parts = []
        for block in blocks:
            btype = block.get("type", "paragraph")
            content = block.get(btype, {})
            rich_text = content.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_text)

            if btype == "heading_1":
                md_parts.append(f"# {text}")
            elif btype == "heading_2":
                md_parts.append(f"## {text}")
            elif btype == "heading_3":
                md_parts.append(f"### {text}")
            elif btype == "bulleted_list_item":
                md_parts.append(f"- {text}")
            elif btype == "numbered_list_item":
                md_parts.append(f"1. {text}")
            elif btype == "to_do":
                checked = content.get("checked", False)
                prefix = "- [x]" if checked else "- [ ]"
                md_parts.append(f"{prefix} {text}")
            elif btype == "code":
                lang = content.get("language", "")
                md_parts.append(f"```{lang}\n{text}\n```")
            elif btype == "quote":
                md_parts.append(f"> {text}")
            elif btype == "divider":
                md_parts.append("---")
            else:
                if text:
                    md_parts.append(text)

            # 递归处理子块
            if content.get("children"):
                md_parts.append(self._blocks_to_markdown(content["children"]))

        return "\n\n".join(md_parts)

    def validate_config(self) -> list[str]:
        """验证 Notion 配置"""
        missing = []
        if not self._token:
            missing.append("token (Notion API Token)")
        if not self._database_id:
            missing.append("database_id (Notion 数据库 ID)")
        return missing
