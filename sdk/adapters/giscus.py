"""
GitHub Pages (Giscus) 评论采集适配器

通过 GitHub Discussions GraphQL API 采集 Giscus 评论。
Giscus 的所有评论实际上存储在 GitHub Discussions 中，
每篇博客文章对应一个 Discussion，评论就是 Discussion 的回复。

能力：
  - fetch_replies()    通过 GraphQL 获取所有 Discussion 评论 ✅
  - test_connection()  测试 API Token 有效性 ✅
"""
import re, json, time
from typing import Optional
from datetime import datetime

try:
    from ..adapter import PlatformAdapter, register, Comment, Article, get_db
except ImportError:
    from sdk.adapter import PlatformAdapter, register, Comment, Article, get_db

import requests


@register
class GiscusAdapter(PlatformAdapter):
    name = "giscus"
    display_name = "GitHub Discussions (Giscus)"
    site_url = "https://duxingkei33.github.io"
    version = "1.0.0"
    description = "通过 GraphQL API 采集 GitHub Discussions (Giscus) 评论"
    icon = "💬"

    config_fields = [
        {
            "key": "github_token",
            "label": "GitHub Token",
            "type": "password",
            "required": True,
            "placeholder": "ghp_xxx...",
        },
        {
            "key": "owner",
            "label": "仓库所有者",
            "type": "text",
            "required": True,
            "default": "duxingkei33",
        },
        {
            "key": "repo",
            "label": "仓库名",
            "type": "text",
            "required": True,
            "default": "duxingkei33.github.io",
        },
        {
            "key": "site_url",
            "label": "博客地址",
            "type": "text",
            "required": False,
            "default": "https://duxingkei33.github.io",
        },
    ]

    GRAPHQL_URL = "https://api.github.com/graphql"

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.token = self.config.get("github_token", "")
        self.owner = self.config.get("owner", "duxingkei33")
        self.repo = self.config.get("repo", "duxingkei33.github.io")
        self.site_url = self.config.get("site_url", "https://duxingkei33.github.io")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _gql(self, query: str, variables: dict = None) -> dict:
        """执行 GraphQL 查询"""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = requests.post(
            self.GRAPHQL_URL,
            json=payload,
            headers=self._headers(),
            timeout=30
        )
        data = resp.json()
        if "errors" in data:
            raise Exception(f"GraphQL Error: {data['errors'][0].get('message', str(data['errors']))}")
        return data.get("data", {})

    def test_connection(self) -> dict:
        """测试 GitHub Token 和仓库访问"""
        try:
            query = """
            query {
              repository(owner: "%s", name: "%s") {
                id
                nameWithOwner
                hasDiscussionsEnabled
              }
            }
            """ % (self.owner, self.repo)
            data = self._gql(query)
            repo = data.get("repository", {})
            if repo.get("hasDiscussionsEnabled"):
                return {
                    "supported": True,
                    "success": True,
                    "error": "",
                    "status": f"已连接 {repo.get('nameWithOwner')}，Discussions 已启用",
                }
            return {
                "supported": True,
                "success": False,
                "error": "该仓库未启用 Discussions",
                "status": "需要启用 Discussions",
            }
        except Exception as e:
            return {
                "supported": True,
                "success": False,
                "error": str(e),
                "status": "连接失败",
            }

    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """
        采集所有博客文章的 Giscus 评论（通过 GitHub Discussions）。
        thread_ids 可以是 discussion_ids，如果为空则采集所有 discussions。
        """
        comments = []

        # 1. 获取所有 Discussions
        discussions = self._fetch_all_discussions()
        if not discussions:
            return comments

        # 2. 对每个 Discussion 获取评论
        for disc in discussions:
            disc_id = disc.get("id", "")
            disc_number = disc.get("number", 0)
            title = disc.get("title", "")
            body = disc.get("body", "") or ""
            url = disc.get("url", "")

            if thread_ids and disc_number not in thread_ids and str(disc_number) not in (thread_ids or []):
                continue

            # 获取所有评论
            disc_comments = self._fetch_discussion_comments(disc_id)
            for c in disc_comments:
                comment = Comment(
                    id=str(c.get("id", "")),
                    author=c.get("author", {}).get("login", "anonymous"),
                    content=c.get("body", ""),
                    created_at=c.get("createdAt", ""),
                    parent_id=c.get("replyTo", {}).get("id", "") if c.get("replyTo") else "",
                    thread_id=str(disc_number),
                )
                comments.append(comment)

            # 节流防限速
            time.sleep(0.3)

        return comments

    def _fetch_all_discussions(self) -> list[dict]:
        """分页获取所有 Discussions"""
        discussions = []
        cursor = None
        has_next = True

        while has_next:
            after = f'after: "{cursor}"' if cursor else ""
            query = """
            query {
              repository(owner: "%s", name: "%s") {
                discussions(first: 100 %s, orderBy: {field: CREATED_AT, direction: DESC}) {
                  totalCount
                  pageInfo { hasNextPage endCursor }
                  nodes {
                    id
                    number
                    title
                    bodyText
                    url
                    createdAt
                  }
                }
              }
            }
            """ % (self.owner, self.repo, after)

            try:
                data = self._gql(query)
                disc_data = data.get("repository", {}).get("discussions", {})
                nodes = disc_data.get("nodes", [])
                discussions.extend(nodes)

                page_info = disc_data.get("pageInfo", {})
                has_next = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor", None)
            except Exception as e:
                print(f"[GiscusAdapter] 获取 Discussions 失败: {e}")
                break

        return discussions

    def _fetch_discussion_comments(self, discussion_id: str) -> list[dict]:
        """分页获取单个 Discussion 的所有评论"""
        all_comments = []
        cursor = None
        has_next = True

        while has_next:
            after = f'after: "{cursor}"' if cursor else ""
            query = """
            query {
              node(id: "%s") {
                ... on Discussion {
                  comments(first: 100 %s) {
                    totalCount
                    pageInfo { hasNextPage endCursor }
                    nodes {
                      id
                      body
                      createdAt
                      author { login }
                      replyTo { id }
                      replies(first: 100) {
                        nodes {
                          id
                          body
                          createdAt
                          author { login }
                        }
                      }
                    }
                  }
                }
              }
            }
            """ % (discussion_id, after)

            try:
                data = self._gql(query)
                comments_data = data.get("node", {}).get("comments", {})
                nodes = comments_data.get("nodes", [])
                all_comments.extend(nodes)

                page_info = comments_data.get("pageInfo", {})
                has_next = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor", None)
            except Exception as e:
                print(f"[GiscusAdapter] 获取评论失败: {e}")
                break

        return all_comments

    def _get_mapping(self) -> str:
        """获取 Giscus 的 mapping 配置（从 DB 或环境）"""
        try:
            # 尝试从 hugo.toml 读取 mapping
            import os
            hugo_path = os.path.expanduser("~/.hermes/github-pages/blog/hugo.toml")
            with open(hugo_path) as f:
                content = f.read()
            m = re.search(r'mapping\s*=\s*"([^"]+)"', content)
            return m.group(1) if m else "pathname"
        except:
            return "pathname"

    def get_article_url_from_discussion(self, discussion) -> str:
        """根据 Discussion 的标题/路径推断博客文章 URL"""
        title = discussion.get("title", "")
        # 从 Discussion body 中提取页面路径
        body = discussion.get("body", "") or ""
        # Giscus 自动创建的 Discussion 的 body 包含页面 URL
        url_match = re.search(r'(https?://[^\s\)"]+)', body)
        if url_match:
            return url_match.group(1)
        # 否则基于 mapping 策略推断
        mapping = self._get_mapping()
        if mapping == "pathname":
            # pathname 策略下，discussion title 通常是页面路径
            path = title.strip("/")
            return f"{self.site_url}/{path}"
        return f"{self.site_url}/"
