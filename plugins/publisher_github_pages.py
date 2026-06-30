"""
GitHub Pages Publisher — 将文章发布为 GitHub Pages 博客的 Markdown 文件
文章会被写入本地仓库的 posts/ 目录，格式化为 MkDocs 兼容的 YAML 前端数据格式
配合 deployer_github_pages.py 完成完整发布流程
支持撤回操作：删除已发布的 Markdown 文件
"""
import os, json
from datetime import datetime
from flashsloth.core.publisher import Publisher, register
from flashsloth.core.article import Article
try:
    from pymdownx.slugs import slugify as _mkdocs_slugify
    _slugger = _mkdocs_slugify(case="lower")
except ImportError:
    _slugger = None


def _get_date_str():
    return datetime.now().strftime("%Y-%m-%d")


@register
class GitHubPagesBlogPublisher(Publisher):
    name = "github_pages_blog"
    display_name = "GitHub Pages 博客"
    description = "将文章发布为 GitHub Pages 博客 Markdown 文件，支持撤回"

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
            "label": "文章 URL 前缀（留空自动用 /YYYY/MM/DD/ 格式）",
            "type": "text",
            "required": False,
            "default": "",
            "placeholder": "留空自动生成",
        },
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.posts_dir = os.path.expanduser(
            config.get("posts_dir", "/opt/data/contenthub/blog/docs/posts")
        )
        self.site_url = config.get("site_url", "https://duxingkei33.github.io").rstrip("/")
        self.post_url_prefix = config.get("post_url_prefix", "")
        # 使用 pymdownx slugify（与 MkDocs Material 一致），否则 fallback
        global _slugger
        if _slugger is None:
            try:
                from pymdownx.slugs import slugify as _mkdocs_slugify
                _slugger = _mkdocs_slugify(case="lower")
            except ImportError:
                _slugger = None

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
        date_str = _get_date_str()
        slug = self._slugify(article.title)
        filename = f"{date_str}-{slug}.md"
        filepath = os.path.join(self.posts_dir, filename)

        # 检查是否已存在
        if os.path.exists(filepath):
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
slug: {slug}
summary: {article.summary or ''}
tags:
{tags_yaml}
---

{article.body}
"""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

            # —— 图片处理：将文章中的图片拷贝到 Hugo 静态目录 ——
            self._copy_article_images(article.body)

            post_slug = filename.replace(".md", "")
            # 生成 MkDocs 兼容的 URL: /YYYY/MM/DD/slug/
            if self.post_url_prefix:
                # 自定义前缀
                prefix = self.post_url_prefix
                if not prefix.startswith("/"):
                    prefix = "/" + prefix
                if not prefix.endswith("/"):
                    prefix = prefix + "/"
                post_url = f"{self.site_url.rstrip('/')}{prefix}{post_slug}/"
            else:
                # 自动用 MkDocs 格式: /YYYY/MM/DD/slug/
                dt = datetime.now()
                y, m, d = dt.year, dt.month, dt.day
                slug = self._slugify(article.title)
                post_url = f"{self.site_url.rstrip('/')}/{y:04d}/{m:02d}/{d:02d}/{slug}/"

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

    def retract(self, article: Article, publish_log: dict = None) -> dict:
        """撤回文章 — 从 posts 目录删除 Markdown 文件"""
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}"}

        if not os.path.isdir(self.posts_dir):
            return {"success": False, "error": f"文章目录不存在: {self.posts_dir}"}

        filepath = None

        # 1. 从发布日志获取文件名
        if publish_log and publish_log.get("message"):
            msg = publish_log.get("message", "")
            if "已写入 " in msg:
                filename = msg.split("已写入 ")[-1].strip()
                filepath = os.path.join(self.posts_dir, filename)

        # 2. 按标题模糊匹配
        if not filepath or not os.path.exists(filepath):
            slug = self._slugify(article.title)
            for fname in os.listdir(self.posts_dir):
                if slug in fname and fname.endswith(".md"):
                    fp = os.path.join(self.posts_dir, fname)
                    if os.path.exists(fp):
                        filepath = fp
                        break

        if not filepath or not os.path.exists(filepath):
            return {"success": False, "error": "找不到对应的文章文件，需手动删除"}

        try:
            os.remove(filepath)
            return {
                "success": True,
                "error": "",
                "message": f"已删除 {os.path.basename(filepath)}，请执行部署以同步到 GitHub Pages",
                "filepath": filepath,
            }
        except OSError as e:
            return {"success": False, "error": f"删除失败: {e}"}

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
        """生成英文 URL slug

        中文标题不使用拼音，自动生成随机英文 slug。
        用户可在文章 frontmatter 中设置 slug 覆盖此值。
        """
        global _slugger

        # 检查是否包含中文字符
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in title)

        if has_chinese:
            # 中文标题 → 随机英文 slug，不要拼音
            import hashlib
            raw = title.encode('utf-8')
            short_hash = hashlib.md5(raw).hexdigest()[:6]
            return f"post-{short_hash}"

        # 纯英文/数字标题 → 正常 slugify
        raw = title

        if _slugger is not None:
            return _slugger(raw, "-")
        # fallback：降级算法
        import re
        slug = raw.lower().strip()
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'[^\w\-]', '', slug)
        slug = re.sub(r'-{2,}', '-', slug)
        slug = slug.strip('-')
        return slug[:80] or "post"

    def _copy_article_images(self, body: str) -> None:
        """扫描文章 body 中的图片引用，从 FlashSloth 上传目录拷贝到 Hugo 静态目录

        图片路径如 /static/uploads/img_1.jpg → 拷贝到 hugo_blog/static/static/uploads/
        这样 Hugo 构建后 /static/uploads/img_1.jpg 可正确访问。
        """
        import re, shutil

        fs_uploads = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "uploads"
        )

        # 从 posts_dir (/opt/data/xxx/blog/content/posts/) 推导 blog 根目录
        blog_root = os.path.dirname(os.path.dirname(os.path.dirname(self.posts_dir)))
        hugo_static = os.path.join(blog_root, "static")

        if not os.path.isdir(fs_uploads):
            return

        # 匹配 <img src="..." /> 中的 src 路径
        for m in re.finditer(r'src="([^"]+)"', body):
            src_path = m.group(1)
            # 只处理 /static/uploads/ 路径
            if not src_path.startswith("/static/uploads/"):
                continue
            rel_path = src_path[len("/static/uploads/"):]
            src_file = os.path.join(fs_uploads, rel_path)
            if not os.path.isfile(src_file):
                continue

            # 目标路径：保留 /static/uploads/ 前导路径
            # Hugo 的 static/ 目录内容从站点根路径服务
            # 要 URL /static/uploads/img.jpg => 文件放 static/static/uploads/img.jpg
            target_dir = os.path.join(hugo_static, "static", "uploads")
            target_file = os.path.join(target_dir, rel_path)
            os.makedirs(target_dir, exist_ok=True)

            # 如果已存在且一致则跳过
            if os.path.isfile(target_file) and os.path.getsize(target_file) == os.path.getsize(src_file):
                continue

            shutil.copy2(src_file, target_file)
