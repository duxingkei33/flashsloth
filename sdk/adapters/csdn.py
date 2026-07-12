"""
CSDN 平台适配器

能力清单：
  - sign_in()             签到（不支持）
  - publish()             发布博客 ✅
  - retract()             撤回（不支持）
  - fetch_posts()         采集博客列表 ✅
  - fetch_replies()       采集回复（不支持）
  - fetch_thread_detail() 读博客详情 ✅
  - reply_comment()       回复评论（不支持）
  - browse_forum()        逛 CSDN 首页 ✅
  - deploy()              部署（不支持）
"""
from typing import Optional
import re
import time

from ..adapter import PlatformAdapter, register, Article, Comment


@register
class CSDNAdapter(PlatformAdapter):
    name = "csdn"
    display_name = "CSDN"
    site_url = "https://blog.csdn.net"
    icon = "📝"
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录 CSDN 后从浏览器复制"},
        {"key": "username", "label": "CSDN 用户名", "type": "text", "required": False,
         "placeholder": "CSDN 博客用户名（用于拼文章列表URL）"},
    ]

    def __init__(self, config=None):
        super().__init__(config)
        self.cookie = (config or {}).get("cookie", "")
        self.username = (config or {}).get("username", "")

    def _make_request(self):
        """创建带Cookie的requests Session"""
        if not self.cookie:
            return None
        import requests
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Cookie": self.cookie,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        return s

    def sign_in(self, check_only: bool = False) -> dict:
        return {"supported": False}

    def publish(self, article: Article, **kwargs) -> dict:
        if not self.cookie:
            return {"supported": True, "success": False, "error": "缺少 Cookie"}
        try:
            from plugins.publisher_csdn import CSDNPublisher
            pub = CSDNPublisher(self.config)
            return pub.publish(article)
        except Exception as e:
            return {"supported": True, "success": False, "error": str(e)}

    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        return {"supported": False}

    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """采集 CSDN 博客文章列表"""
        if not self.cookie or not self.username:
            return []
        s = self._make_request()
        if not s:
            return []

        articles = []
        try:
            for page in range(1, max_pages + 1):
                url = f"https://blog.csdn.net/{self.username}/article/list/{page}"
                resp = s.get(url, timeout=10)
                if resp.status_code != 200:
                    break

                for m in re.finditer(
                    r'<h4[^>]*class="title"[^>]*>.*?<a[^>]*href="[^"]*article/details/(\d+)"[^>]*>(.*?)</a>',
                    resp.text, re.DOTALL
                ):
                    aid = m.group(1)
                    title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                    if not title:
                        continue
                    articles.append(Article(
                        title=title, source="csdn",
                        source_url=f"https://blog.csdn.net/{self.username}/article/details/{aid}",
                        source_id=aid, body="",
                        raw={"id": aid, "username": self.username},
                    ))
                time.sleep(0.5)
            return articles
        except Exception:
            return []

    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        return []

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """获取 CSDN 博客文章详情"""
        if not thread_id or not self.cookie:
            return None
        s = self._make_request()
        if not s:
            return None
        try:
            username = self.username
            url = f"https://blog.csdn.net/{username}/article/details/{thread_id}"
            resp = s.get(url, timeout=10)
            if resp.status_code != 200:
                return None

            title_m = re.search(r'<h1[^>]*class="title-article"[^>]*>(.*?)</h1>', resp.text, re.DOTALL)
            title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

            body_m = re.search(r'<article[^>]*class="baidu_pl"[^>]*>(.*?)</article>', resp.text, re.DOTALL)
            if not body_m:
                body_m = re.search(r'<div[^>]*id="article_content"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
            body = body_m.group(1).strip() if body_m else ""

            tags = []
            for tm in re.finditer(r'<a[^>]*class="tag-link"[^>]*>(.*?)</a>', resp.text):
                tags.append(re.sub(r"<[^>]+>", "", tm.group(1)).strip())

            return Article(
                title=title, body=body, source="csdn",
                source_url=url, source_id=thread_id,
                tags=tags, raw={"id": thread_id},
            )
        except Exception:
            return None

    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        return {"supported": False}

    def browse_forum(self, **kwargs) -> dict:
        """浏览 CSDN 首页推荐"""
        try:
            s = self._make_request()
            if not s:
                return {"supported": True, "total": 0, "error": "Cookie 未配置"}
            resp = s.get("https://blog.csdn.net", timeout=10)
            articles = []
            for m in re.finditer(
                r'<a[^>]*href="(https://blog\.csdn\.net/[^"]+/article/details/\d+)"[^>]*>(.*?)</a>',
                resp.text, re.DOTALL
            ):
                url = m.group(1)
                title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                if title and len(title) > 5:
                    articles.append({"title": title, "url": url})
            return {
                "supported": True, "total": len(articles),
                "filtered": 0, "new_saved": 0,
                "articles": articles[:20],
            }
        except Exception as e:
            return {"supported": True, "total": 0, "error": str(e)}

    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        return {"supported": False}

    def test_connection(self) -> dict:
        if not self.cookie:
            return {"supported": True, "success": False, "error": "Cookie 未配置"}
        try:
            s = self._make_request()
            resp = s.get("https://blog.csdn.net", timeout=10)
            if "passport.csdn.net" in resp.url or "login" in resp.url.lower():
                return {"supported": True, "success": False, "error": "Cookie 已过期", "status": "Cookie 过期"}
            return {"supported": True, "success": True, "status": "Cookie 有效"}
        except Exception as e:
            return {"supported": True, "success": False, "error": str(e)}
