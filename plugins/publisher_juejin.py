"""
掘金 Publisher — 模拟浏览器请求
掘金无官方公开 API，用 Cookie 鉴权模拟发布
"""
import requests, re
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class JuejinPublisher(Publisher):
    name = "juejin"
    display_name = "掘金"
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录掘金后从浏览器 F12 复制"},
    ]

    BASE_URL = "https://api.juejin.cn"

    def __init__(self, config: dict):
        super().__init__(config)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Cookie": config.get("cookie", ""),
            "Content-Type": "application/json",
        }

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: Cookie",
                    "url": "", "id": ""}

        try:
            # 1. 获取用户信息（验证 Cookie 有效性）
            user_resp = requests.get(
                f"{self.BASE_URL}/user_api/v1/user/get",
                headers=self.headers,
                timeout=10,
            )
            if user_resp.status_code != 200:
                return {"success": False, "error": "Cookie 无效或已过期",
                        "url": "", "id": ""}

            # 2. 创建草稿（先存为草稿，再发布）
            draft_data = {
                "title": article.title,
                "mark_content": article.body,
                "brief": (article.summary or "")[:200],
                "category_id": "1",  # 后端
                "tag_ids": [],
                "cover": article.cover or "",
                "is_show_cover": 1 if article.cover else 0,
            }

            draft_resp = requests.post(
                f"{self.BASE_URL}/content_api/v1/article_draft/create",
                json=draft_data,
                headers=self.headers,
                timeout=15,
            )
            draft_result = draft_resp.json()
            draft_id = draft_result.get("data", {}).get("id")
            if not draft_id:
                return {"success": False, "error": f"草稿创建失败: {draft_result}",
                        "url": "", "id": ""}

            # 3. 发布草稿
            publish_resp = requests.post(
                f"{self.BASE_URL}/content_api/v1/article/publish",
                json={"draft_id": draft_id, "sync_to_org": 0},
                headers=self.headers,
                timeout=15,
            )
            pub_result = publish_resp.json()
            article_id = pub_result.get("data", {}).get("article_id", draft_id)

            return {
                "success": True,
                "url": f"https://juejin.cn/post/{article_id}",
                "id": article_id,
                "error": "",
            }

        except Exception as e:
            return {"success": False, "error": f"掘金发布异常: {e}", "url": "", "id": ""}
