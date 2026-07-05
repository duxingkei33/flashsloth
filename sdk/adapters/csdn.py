"""
CSDN 平台适配器

能力清单：
  - sign_in()             签到（不支持）
  - publish()             发布博客 ✅
  - retract()             撤回（不支持）
  - fetch_posts()         采集（不支持）
  - fetch_replies()       采集回复（不支持）
  - fetch_thread_detail() 读帖详情（不支持）
  - reply_comment()       回复评论（不支持）
  - browse_forum()        逛论坛（不支持）
  - deploy()              部署（不支持）
"""
from ..adapter import PlatformAdapter, register, Article, Comment
from typing import Optional


@register
class CSDNAdapter(PlatformAdapter):
    name = "csdn"
    display_name = "CSDN"
    site_url = "https://blog.csdn.net"
    icon = "📝"
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录 CSDN 后从浏览器复制"},
    ]

    def __init__(self, config=None):
        super().__init__(config)
        self.cookie = (config or {}).get("cookie", "")

    # ─── 签到 ─────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """CSDN 不支持每日签到"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────
    def publish(self, article: Article, **kwargs) -> dict:
        if not self.cookie:
            return {"supported": True, "success": False, "error": "缺少 Cookie"}
        try:
            from plugins.publisher_csdn import CSDNPublisher
            pub = CSDNPublisher(self.config)
            return pub.publish(article)
        except Exception as e:
            return {"supported": True, "success": False, "error": str(e)}

    # ─── 撤回 ─────────────────────────────────
    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """CSDN 暂不支持通过 API 撤回已发布的博客"""
        return {"supported": False}

    # ─── 采集帖子 ─────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """CSDN 暂不支持自动采集博客"""
        return []

    # ─── 采集回复 ─────────────────────────────
    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """CSDN 暂不支持批量采集评论"""
        return []

    # ─── 读帖详情 ─────────────────────────────
    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """CSDN 暂不支持按 ID 获取博客详情"""
        return None

    # ─── 回复评论 ─────────────────────────────
    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """CSDN 暂不支持自动回复评论"""
        return {"supported": False}

    # ─── 逛论坛 ───────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """CSDN 暂不支持刷信息流"""
        return {"supported": False}

    # ─── 部署 ─────────────────────────────────
    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        """CSDN 不涉及站点部署"""
        return {"supported": False}

    # ─── 测试连接 ─────────────────────────────
    def test_connection(self) -> dict:
        if not self.cookie:
            return {"supported": True, "success": False, "error": "Cookie 未配置"}
        return {"supported": True, "success": True, "status": "Cookie 已配置"}
