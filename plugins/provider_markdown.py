"""MarkdownProvider — 从 posts/ 目录读取 .md 文件作为内容来源"""
import os
import re
from datetime import datetime
from typing import Optional

from flashsloth.core.provider import Provider, ContentItem, register_provider


@register_provider
class MarkdownProvider(Provider):
    name = "markdown"
    display_name = "Markdown 文件"
    description = "从 posts/ 目录扫描 .md 文件"
    icon = "📁"
    config_fields = [
        {"key": "watch_dir", "label": "监控目录", "type": "text", "default": "", "hint": "留空用默认 posts/ 目录", "required": False},
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self._posts_dir = (config or {}).get(
            "watch_dir",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "posts"),
        )

    def list_items(self) -> list[ContentItem]:
        """扫描 posts/ 目录下的所有 .md 文件"""
        items = []
        if not os.path.isdir(self._posts_dir):
            return items

        for fname in sorted(os.listdir(self._posts_dir), reverse=True):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(self._posts_dir, fname)
            try:
                stat = os.stat(fpath)
                # 读取前几行提取标题
                title = fname.replace(".md", "")
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(2048)
                # 尝试从 YAML frontmatter 或首行 # 标题提取
                title_match = re.search(r'^title:\s*(.+)', head, re.MULTILINE)
                if title_match:
                    title = title_match.group(1).strip()
                elif head.startswith("# "):
                    title = head.split("\n")[0].lstrip("# ").strip()
                # 提取摘要
                body = head
                summary = ""
                for line in body.split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("---"):
                        summary = line[:120]
                        break

                items.append(ContentItem(
                    id=fname,
                    title=title,
                    summary=summary,
                    source="markdown",
                    tags=[],
                    created_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    raw_data={"path": fpath, "size": stat.st_size},
                ))
            except Exception:
                continue
        return items

    def get_item(self, item_id: str) -> Optional[ContentItem]:
        """获取单个 .md 文件的元数据"""
        for item in self.list_items():
            if item.id == item_id:
                return item
        return None

    def get_item_content(self, item_id: str) -> str:
        """读取 .md 文件全部内容"""
        fpath = os.path.join(self._posts_dir, item_id)
        if not os.path.isfile(fpath):
            # 也尝试不加 .md 后缀
            if not item_id.endswith(".md"):
                fpath = os.path.join(self._posts_dir, item_id + ".md")
        if not os.path.isfile(fpath):
            return ""
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
