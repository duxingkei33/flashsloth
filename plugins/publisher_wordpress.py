"""
WordPress Publisher — 通过 REST API 发布
稳定方案，WordPress 自带 REST API，无需插件
"""
import requests
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class WordPressPublisher(Publisher):
    name = "wordpress"
    display_name = "WordPress"
    login_methods = [
        {"method": "password", "label": "应用密码认证", "icon": "🔑", "priority": 1,
         "fields": ["site_url", "username", "app_password"],
         "description": "使用 WordPress 应用密码通过 REST API 认证"},
    ]
    config_fields = [
        {"key": "site_url", "label": "站点 URL", "type": "text", "required": True,
         "placeholder": "https://yourblog.com"},
        {"key": "username", "label": "用户名", "type": "text", "required": True},
        {"key": "app_password", "label": "应用密码", "type": "password", "required": True},
        {"key": "default_status", "label": "默认状态", "type": "select",
         "options": ["draft", "publish", "pending"], "default": "draft"},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.site_url = config.get("site_url", "").rstrip("/")
        self.api_url = f"{self.site_url}/wp-json/wp/v2"
        self.auth = (config.get("username", ""), config.get("app_password", ""))
        self.default_status = config.get("default_status", "draft")

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        # 构建正文（WordPress 用 HTML）
        html_body = article.to_html()

        # 构建分类标签
        categories = []
        tags = []
        for t in article.tags:
            cat_id = self._get_or_create_category(t)
            if cat_id:
                categories.append(cat_id)
            tag_id = self._get_or_create_tag(t)
            if tag_id:
                tags.append(tag_id)

        data = {
            "title": article.title,
            "content": html_body,
            "status": kwargs.get("status", self.default_status),
        }
        if article.summary:
            data["excerpt"] = article.summary
        if categories:
            data["categories"] = categories
        if tags:
            data["tags"] = tags

        try:
            resp = requests.post(
                f"{self.api_url}/posts",
                json=data,
                auth=self.auth,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
            return {
                "success": True,
                "url": result.get("link", ""),
                "id": str(result.get("id", "")),
                "error": "",
            }
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"HTTP 错误: {e}",
                    "url": "", "id": ""}

    def _get_or_create_category(self, name: str) -> int | None:
        """获取或创建分类"""
        try:
            resp = requests.get(
                f"{self.api_url}/categories",
                params={"search": name},
                auth=self.auth,
                timeout=10,
            )
            results = resp.json()
            if results and isinstance(results, list):
                return results[0]["id"]
            # 创建
            resp = requests.post(
                f"{self.api_url}/categories",
                json={"name": name},
                auth=self.auth,
                timeout=10,
            )
            if resp.ok:
                return resp.json().get("id")
        except Exception:
            pass
        return None

    def _get_or_create_tag(self, name: str) -> int | None:
        """获取或创建标签"""
        try:
            resp = requests.get(
                f"{self.api_url}/tags",
                params={"search": name},
                auth=self.auth,
                timeout=10,
            )
            results = resp.json()
            if results and isinstance(results, list):
                return results[0]["id"]
            resp = requests.post(
                f"{self.api_url}/tags",
                json={"name": name},
                auth=self.auth,
                timeout=10,
            )
            if resp.ok:
                return resp.json().get("id")
        except Exception:
            pass
        return None
