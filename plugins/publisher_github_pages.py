"""
GitHub Pages Publisher — 发布文章到 MkDocs / GitHub Pages 博客
文章保存为 Markdown 文件到指定目录，由自动构建流程推送到 GitHub Pages
"""
import os, json, re
from datetime import datetime
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register


@register
class GitHubPagesPublisher(Publisher):
    name = "github_pages"
    display_name = "GitHub Pages 博客"
    config_fields = [
        {"key": "output_dir", "label": "文章输出目录", "type": "text", "required": True,
         "default": "/opt/data/contenthub/blog/docs/posts",
         "placeholder": "存放 .md 文件的目录路径"},
        {"key": "site_url", "label": "博客地址", "type": "text", "required": False,
         "default": "https://duxingkei33.github.io",
         "placeholder": "https://duxingkei33.github.io"},
        {"key": "blog_name", "label": "博客名称", "type": "text", "required": False,
         "default": "FlashSloth Blog", "placeholder": "博客名称"},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.output_dir = config.get("output_dir", "/opt/data/contenthub/blog/docs/posts")
        self.site_url = config.get("site_url", "https://duxingkei33.github.io")
        self.blog_name = config.get("blog_name", "FlashSloth Blog")

    def publish(self, article: Article, **kwargs) -> dict:
        """发布文章到 GitHub Pages — 写 Markdown 文件到 posts 目录"""
        if not article.title:
            return {"success": False, "error": "文章标题不能为空", "url": "", "id": ""}

        # 生成 slug
        slug = self._make_slug(article.title)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}-{slug}.md"
        filepath = os.path.join(self.output_dir, filename)

        # 构建 Frontmatter
        tags = article.tags or []
        tags_str = json.dumps(tags, ensure_ascii=False) if tags else "[]"
        summary = article.summary or ""

        frontmatter = f"""---
title: "{article.title}"
date: {date_str}
tags: {tags_str}
description: {summary}
---

"""
        md_content = frontmatter + (article.body or "")

        # 确保目录存在
        os.makedirs(self.output_dir, exist_ok=True)

        # 写入文件
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)
        except Exception as e:
            return {"success": False, "error": f"文件写入失败: {e}", "url": "", "id": slug}

        # 返回文章 URL
        post_url = f"{self.site_url}/posts/{slug}/"
        return {
            "success": True,
            "url": post_url,
            "id": slug,
            "error": "",
        }

    def _make_slug(self, title: str) -> str:
        """生成 URL 友好的 slug"""
        # 替换中文和空格为横线
        slug = title.lower().strip()
        # 保留字母数字和横线，其他转横线
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug)
        slug = slug.strip('-')
        # 如果全是非英文字符导致 slug 为空，用时间戳
        if not slug:
            slug = datetime.now().strftime("post-%Y%m%d%H%M%S")
        return slug[:80]
