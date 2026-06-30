"""
GitHub Pages Platform Adapter — 将文章发布到 GitHub Pages 博客

实现 publish()（写入 Markdown 文件到 posts 目录）和 deploy()（git push 到 GitHub）。
包装现有 plugins/publisher_github_pages.py 和 plugins/deployer_github_pages.py。

支持的接口:
  - sign_in()     不支持（GitHub Pages 无签到）
  - publish()     写入 Markdown 文章到 posts 目录 ✅
  - retract()     撤回已发布的文章（删除 Markdown 文件）✅
  - fetch_posts() 不支持（非内容源）
  - fetch_replies() 不支持
  - fetch_thread_detail() 不支持
  - reply_comment() 不支持
  - browse_forum() 不支持（非论坛）
  - deploy()      git commit + push 部署到 GitHub Pages ✅
"""
import os
from typing import Optional

from ..adapter import PlatformAdapter, register, Article, get_db


@register
class GitHubPagesAdapter(PlatformAdapter):
    name = "github_pages"
    display_name = "GitHub Pages"
    site_url = "https://duxingkei33.github.io"
    version = "1.0.0"
    description = "将文章发布为 GitHub Pages 博客 — 写入 Markdown 文件后执行 git push 部署"
    icon = "📄"

    config_fields = [
        {
            "key": "github_username",
            "label": "GitHub 用户名",
            "type": "text",
            "required": True,
            "placeholder": "duxingkei33",
        },
        {
            "key": "github_token",
            "label": "GitHub Token (Personal Access Token)",
            "type": "password",
            "required": True,
            "placeholder": "***",
        },
        {
            "key": "repo",
            "label": "仓库 (owner/repo)",
            "type": "text",
            "required": True,
            "default": "duxingkei33/duxingkei33.github.io",
            "placeholder": "用户名/仓库名",
        },
        {
            "key": "repo_dir",
            "label": "本地仓库目录",
            "type": "text",
            "required": True,
            "default": "/opt/data/contenthub",
            "placeholder": "GitHub Pages 仓库的本地路径",
        },
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
        {
            "key": "branch",
            "label": "分支",
            "type": "text",
            "required": False,
            "default": "main",
            "placeholder": "main",
        },
        {
            "key": "commit_prefix",
            "label": "提交前缀",
            "type": "text",
            "required": False,
            "default": "deploy",
            "placeholder": "deploy",
        },
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        cfg = config or {}
        self.github_username = cfg.get("github_username", "")
        self.github_token = cfg.get("github_token", "")
        self.repo = cfg.get("repo", "")
        self.repo_dir = os.path.expanduser(
            cfg.get("repo_dir", "/opt/data/contenthub")
        )
        self.posts_dir = os.path.expanduser(
            cfg.get("posts_dir", "/opt/data/contenthub/blog/docs/posts")
        )
        self.site_url = cfg.get(
            "site_url", "https://duxingkei33.github.io"
        ).rstrip("/")
        self.post_url_prefix = cfg.get("post_url_prefix", "")
        self.branch = cfg.get("branch", "main")
        self.commit_prefix = cfg.get("commit_prefix", "deploy")

    def validate_config(self) -> list[str]:
        """检查配置完整性"""
        missing = []
        if not self.github_username:
            missing.append("GitHub 用户名")
        if not self.github_token:
            missing.append("GitHub Token")
        if not self.repo:
            missing.append("仓库")
        if not self.posts_dir:
            missing.append("博客文章目录")
        return missing

    # ─── 签到 ─────────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """GitHub Pages 无签到功能"""
        return {"supported": False}

    # ─── 采集帖子 ─────────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list:
        """GitHub Pages 非内容源，不支持采集"""
        return []

    # ─── 采集回复 ─────────────────────────────────
    def fetch_replies(self, thread_ids: list = None, **kwargs) -> list:
        """GitHub Pages 非评论平台"""
        return []

    # ─── 读帖详情 ─────────────────────────────────
    def fetch_thread_detail(self, thread_id: str) -> None:
        """GitHub Pages 不支持按 ID 获取文章详情"""
        return None

    # ─── 回复评论 ─────────────────────────────────
    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """GitHub Pages 不支持回复评论"""
        return {"supported": False}

    # ─── 逛论坛 ───────────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """GitHub Pages 非论坛"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────────
    def _make_publisher(self) -> object:
        """创建 GitHub Pages 博客发布器"""
        from plugins.publisher_github_pages import GitHubPagesBlogPublisher

        return GitHubPagesBlogPublisher(
            {
                "posts_dir": self.posts_dir,
                "site_url": self.site_url,
                "post_url_prefix": self.post_url_prefix,
            }
        )

    def _make_deployer(self) -> object:
        """创建 GitHub Pages 部署器"""
        from plugins.deployer_github_pages import GitHubPagesDeployer

        return GitHubPagesDeployer(
            {
                "github_username": self.github_username,
                "github_token": self.github_token,
                "repo": self.repo,
                "repo_dir": self.repo_dir,
                "site_url": self.site_url,
                "branch": self.branch,
                "commit_prefix": self.commit_prefix,
            }
        )

    # ─── 发布 ─────────────────────────────────────

    def publish(self, article: Article, **kwargs) -> dict:
        """
        将文章发布为 GitHub Pages 博客的 Markdown 文件。

        委托给 plugins/publisher_github_pages.py 的 GitHubPagesBlogPublisher。
        返回: {"supported": bool, "success": bool, "url": str, "id": str,
                 "error": str, "message": str, "filepath": str}
        """
        if "check_only" in kwargs:
            return {"supported": True, "message": "支持 GitHub Pages 博客发布"}

        missing = self.validate_config()
        if missing:
            return {
                "supported": True,
                "success": False,
                "url": "",
                "id": "",
                "error": f"缺少配置: {', '.join(missing)}",
                "message": "",
            }

        try:
            publisher = self._make_publisher()
            result = publisher.publish(article)

            # 统一返回格式
            return {
                "supported": True,
                "success": result.get("success", False),
                "url": result.get("url", ""),
                "id": result.get("filepath", ""),
                "error": result.get("error", ""),
                "message": result.get("message", ""),
                "filepath": result.get("filepath", ""),
            }

        except Exception as e:
            return {
                "supported": True,
                "success": False,
                "url": "",
                "id": "",
                "error": f"发布异常: {e}",
                "message": "",
            }

    # ─── 撤回 ─────────────────────────────────────

    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """
        撤回已发布的文章 — 从 posts 目录删除对应的 Markdown 文件。

        返回: {"supported": bool, "success": bool, "error": str, "message": str}
        """
        missing = self.validate_config()
        if missing:
            return {
                "supported": True,
                "success": False,
                "error": f"缺少配置: {', '.join(missing)}",
                "message": "",
            }

        try:
            publisher = self._make_publisher()
            # 构造一个 Article 对象（只需要 title 字段用于匹配）
            article = Article(title=article_id)
            result = publisher.retract(article, publish_log)

            return {
                "supported": True,
                "success": result.get("success", False),
                "error": result.get("error", ""),
                "message": result.get("message", ""),
            }

        except Exception as e:
            return {
                "supported": True,
                "success": False,
                "error": f"撤回异常: {e}",
                "message": "",
            }

    # ─── 部署 ─────────────────────────────────────

    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        """
        执行 git commit + push 部署到 GitHub Pages。

        委托给 plugins/deployer_github_pages.py 的 GitHubPagesDeployer。
        返回: {"supported": bool, "success": bool, "url": str,
                 "error": str, "message": str}
        """
        if check_only:
            return {"supported": True, "message": "支持 git push 部署到 GitHub Pages"}

        missing = self.validate_config()
        if missing:
            return {
                "supported": True,
                "success": False,
                "url": "",
                "error": f"缺少配置: {', '.join(missing)}",
                "message": "",
            }

        try:
            deployer = self._make_deployer()
            result = deployer.deploy()

            return {
                "supported": True,
                "success": result.get("success", False),
                "url": result.get("url", self.site_url),
                "error": result.get("error", ""),
                "message": result.get("message", ""),
            }

        except Exception as e:
            return {
                "supported": True,
                "success": False,
                "url": "",
                "error": f"部署异常: {e}",
                "message": "",
            }

    # ─── 测试连接 ─────────────────────────────────

    def test_connection(self) -> dict:
        """测试配置是否完整、posts 目录是否可写、GitHub Token 是否有效"""
        missing = self.validate_config()
        if missing:
            return {
                "supported": True,
                "success": False,
                "error": f"缺少配置: {', '.join(missing)}",
                "status": "配置不完整",
            }

        # 1. 测试 posts 目录
        publisher = self._make_publisher()
        pub_test = publisher.test_connection()
        if not pub_test.get("success", False):
            return {
                "supported": True,
                "success": False,
                "error": pub_test.get("error", "文章目录不可用"),
                "status": pub_test.get("status", "失败"),
            }

        # 2. 测试仓库和 Token
        deployer = self._make_deployer()
        dep_test = deployer.test_connection()
        if not dep_test.get("success", False):
            return {
                "supported": True,
                "success": False,
                "error": dep_test.get("error", "部署配置不可用"),
                "status": dep_test.get("status", "失败"),
            }

        return {
            "supported": True,
            "success": True,
            "error": "",
            "status": (
                f"文章目录可写，Token 有效，仓库正常: {self.repo}"
            ),
        }
