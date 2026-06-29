"""
GitHub Pages Publisher — 将文章发布为 GitHub Pages 博客的 Markdown 文件
文章会被写入本地仓库的 posts/ 目录，格式化为 MkDocs 兼容的 YAML 前端数据格式
配合 deployer_github_pages.py 完成完整发布流程
"""
import os, json
from datetime import datetime
from flashsloth.core.publisher import Publisher, register
from flashsloth.core.article import Article


@register
class GitHubPagesBlogPublisher(Publisher):
    name = "github_pages_blog"
    display_name = "GitHub Pages 博客"
    description = "将文章发布为 GitHub Pages 博客 Markdown 文件"

    config_fields = [
        {
            "key": "posts_dir",
            "label": "博客文章目录",
            "type": "text",
            "required": True,
            "default": "/opt/data/contenthub/blog/docs/posts",
            "placeholder": "Markdown 文章存放目录",
        },
        {
            "key": "site_url",
            "label": "博客地址",
            "type": "text",
            "required": False,
            "default": "https://duxingkei33.github.io",
            "placeholder": "https://duxingkei33.github.io",
        },
        {
            "key": "post_url_prefix",
            "label": "文章 URL 前缀",
            "type": "text",
            "required": False,
            "default": "/posts/",
            "placeholder": "/posts/",
        },
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.posts_dir = os.path.expanduser(
            config.get("posts_dir", "/opt/data/contenthub/blog/docs/posts")
        )
        self.site_url = config.get("site_url", "https://duxingkei33.github.io").rstrip("/")
        self.post_url_prefix = config.get("post_url_prefix", "/posts/")

    def publish(self, article: Article) -> dict:
        """将文章发布为 Markdown 文件"""
        missing = self.validate_config()
        if missing:
            return {
                "success": False,
                "error": f"缺少配置: {', '.join(missing)}",
                "url": "",
            }

        if not os.path.isdir(self.posts_dir):
            try:
                os.makedirs(self.posts_dir, exist_ok=True)
            except OSError as e:
                return {
                    "success": False,
                    "error": f"无法创建目录: {e}",
                    "url": "",
                }

        # 生成文件名: YYYY-MM-DD-文章标题.md
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = self._slugify(article.title)
        filename = f"{date_str}-{slug}.md"
        filepath = os.path.join(self.posts_dir, filename)

        # 检查是否已存在（防止覆盖）
        if os.path.exists(filepath):
            # 加序号
            counter = 1
            while os.path.exists(filepath):
                filename = f"{date_str}-{slug}-{counter}.md"
                filepath = os.path.join(self.posts_dir, filename)
                counter += 1

        # 生成 Markdown 内容（带 YAML 前端数据）
        tags = article.tags or []
        tags_yaml = "\n".join([f"  - {t}" for t in tags]) if tags else ""

        md_content = f"""---
title: {article.title}
date: {date_str}
summary: {article.summary or ''}
tags:
{tags_yaml}
---

{article.body}
"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            # 计算文章 URL
            post_url = f"{self.site_url}{self.post_url_prefix.strip('/')}/{slug}/"
            # 如果 mkdocs 的命名规则不同，取文件名不带扩展名
            post_slug = filename.replace(".md", "")
            post_url = f"{self.site_url}{self.post_url_prefix.strip('/')}/{post_slug}/"

            return {
                "success": True,
                "url": post_url,
                "error": "",
                "message": f"已写入 {filename}",
                "filepath": filepath,
            }

        except OSError as e:
            return {
                "success": False,
                "error": f"写入文件失败: {e}",
                "url": "",
            }

    def test_connection(self) -> dict:
        """测试文章目录是否可写"""
        if not os.path.isdir(self.posts_dir):
            try:
                os.makedirs(self.posts_dir, exist_ok=True)
                return {"success": True, "error": "", "status": "目录已创建"}
            except OSError as e:
                return {
                    "success": False,
                    "error": f"无法创建目录: {e}",
                    "status": "失败",
                }
        test_file = os.path.join(self.posts_dir, ".write_test")
        try:
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return {"success": True, "error": "", "status": f"目录可写: {self.posts_dir}"}
        except OSError as e:
            return {
                "success": False,
                "error": str(e),
                "status": "目录不可写",
            }

    def _slugify(self, title: str) -> str:
        """将标题转为 URL 友好的 slug"""
        import re
        # 中文保留，空格和特殊字符转横线
        slug = title.lower().strip()
        # 替换空格和特殊字符为横线
        slug = re.sub(r'[\s_]+', '-', slug)
        # 只保留字母数字和中文和横线
        slug = re.sub(r'[^\w\-]', '', slug)
        # 去掉多余的横线
        slug = re.sub(r'-{2,}', '-', slug)
        slug = slug.strip('-')
        return slug[:80] or "post"
