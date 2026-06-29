"""Article — FlashSloth 统一数据模型"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Article:
    """全系统统一文章模型"""
    title: str
    body: str                          # Markdown 正文
    summary: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    cover: Optional[str] = None        # 封面图 URL
    assets: list[str] = field(default_factory=list)
    slug: Optional[str] = None         # URL 路径
    date: Optional[str] = None
    status: str = "draft"              # draft | ready | published
    source: Optional[str] = None       # 来源标识
    metadata: dict = field(default_factory=dict)

    def to_markdown(self) -> str:
        """转 frontmatter Markdown（MkDocs/Hexo 兼容）"""
        lines = ["---"]
        lines.append(f'title: "{self.title}"')
        if self.date:
            lines.append(f"date: {self.date}")
        if self.tags:
            lines.append(f"tags: [{', '.join(self.tags)}]")
        if self.summary:
            lines.append(f"description: {self.summary}")
        if self.cover:
            lines.append(f"cover: {self.cover}")
        if self.slug:
            lines.append(f"slug: {self.slug}")
        for k, v in self.metadata.items():
            lines.append(f"{k}: {v}")
        lines.append("---\n")
        lines.append(self.body)
        return "\n".join(lines)

    def to_html(self) -> str:
        """Markdown → HTML"""
        import markdown
        return markdown.markdown(
            self.body,
            extensions=["extra", "codehilite", "toc", "sane_lists"]
        )

    @classmethod
    def from_markdown(cls, text: str) -> "Article":
        """从 frontmatter Markdown 解析"""
        import frontmatter, yaml
        try:
            fm = frontmatter.loads(text)
        except Exception:
            # 纯 Markdown 无 frontmatter
            return cls(title="", body=text)
        return cls(
            title=fm.get("title", ""),
            body=fm.content,
            summary=fm.get("description") or fm.get("summary"),
            tags=fm.get("tags", []),
            cover=fm.get("cover"),
            slug=fm.get("slug"),
            date=str(fm.get("date", "")),
            metadata={k: v for k, v in fm.metadata.items()
                      if k not in ("title", "date", "tags", "description", "summary", "cover", "slug")},
        )
