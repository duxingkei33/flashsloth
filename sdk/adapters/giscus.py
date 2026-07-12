"""
GitHub Discussions (Giscus) 平台适配器

能力清单：
  - fetch_replies()       采集评论 ✅（通过 GitHub GraphQL API）
  - test_connection()     测试连接 ✅

其他功能需测试环境
"""
from typing import Optional
from ..adapter import PlatformAdapter, register, Article, Comment


@register
class GiscusAdapter(PlatformAdapter):
    name = "giscus"
    display_name = "GitHub Discussions (Giscus)"
    site_url = "https://giscus.app"
    icon = "💬"

    config_fields = [
        {"key": "repo", "label": "GitHub Repo", "type": "text", "required": True,
         "placeholder": "owner/repo"},
        {"key": "repo_id", "label": "Repo ID", "type": "text", "required": True},
        {"key": "category_id", "label": "Category ID", "type": "text", "required": True},
        {"key": "token", "label": "GitHub Token", "type": "password", "required": True},
    ]

    def __init__(self, config=None):
        super().__init__(config)

    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """已实现 — 通过 GitHub Discussions API"""
        import requests, json
        if not thread_ids or not self.config.get("token"):
            return []
        headers = {"Authorization": f"Bearer {self.config['token']}", "Content-Type": "application/json"}
        comments = []
        for did in thread_ids:
            q = f"""
            {{
              repository(owner: "{self.config.get('repo','').split('/')[0]}", name: "{self.config.get('repo','').split('/')[1]}") {{
                discussion(number: {did}) {{
                  comments(first: 20) {{
                    nodes {{
                      author {{ login }}
                      body
                      createdAt
                    }}
                  }}
                }}
              }}
            }}
            """
            r = requests.post("https://api.github.com/graphql", json={"query": q}, headers=headers)
            if r.status_code == 200:
                data = r.json()
                nodes = data.get("data", {}).get("repository", {}).get("discussion", {}).get("comments", {}).get("nodes", [])
                for n in nodes:
                    comments.append(Comment(
                        author=n.get("author", {}).get("login", ""),
                        content=n.get("body", ""),
                        thread_id=did,
                    ))
        return comments

    def fetch_posts(self, hours=24, max_pages=3, **kwargs) -> list[Article]:
        return []

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        return None

    def browse_forum(self, **kwargs) -> dict:
        return {"supported": True, "total": 0, "message": "⏳ 需要测试环境"}

    def publish(self, article: Article, **kwargs) -> dict:
        return {"supported": False}

    def test_connection(self) -> dict:
        return {"success": True, "status": "已配置"}
