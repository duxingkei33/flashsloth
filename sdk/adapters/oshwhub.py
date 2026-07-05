"""
立创开源硬件平台 (oshwhub.com) 平台适配器

oshwhub.com 是嘉立创 EDA 生态的开源硬件分享平台，Next.js + Ant Design 构建。
非 Discuz 系平台，独立适配。

能力清单：
  - sign_in()             签到（不支持，使用独立签到插件）
  - publish()             发布项目 ✅（通过 Playwright 浏览器自动化或 Cookie API）
  - retract()             撤回（不支持）
  - fetch_posts()         采集项目 ✅
  - fetch_replies()       采集评论（不支持）
  - fetch_thread_detail() 读项目详情 ✅
  - reply_comment()       回复评论（不支持）
  - browse_forum()        逛平台 ✅
  - deploy()              部署（不支持）
"""
from typing import Optional
import json, time, os, re

from ..adapter import PlatformAdapter, register, Article, Comment


@register
class OshwhubAdapter(PlatformAdapter):
    name = "oshwhub"
    display_name = "立创开源硬件平台"
    site_url = "https://oshwhub.com"
    version = "1.0.0"
    description = "立创开源硬件平台 — 嘉立创 EDA 生态，优质硬件创作分享平台"
    icon = "🔌"

    config_fields = [
        {"key": "site_url", "label": "平台地址", "type": "text", "required": True,
         "default": "https://oshwhub.com",
         "placeholder": "https://oshwhub.com"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": False,
         "placeholder": "登录后从浏览器 F12 复制 Cookie"},
        {"key": "username", "label": "用户名/邮箱", "type": "text", "required": False,
         "placeholder": "OSHWHub 登录用户名或邮箱"},
        {"key": "password", "label": "密码", "type": "password", "required": False,
         "placeholder": "OSHWHub 登录密码"},
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        if not self.config.get("site_url"):
            self.config["site_url"] = "https://oshwhub.com"
        self.username = (config or {}).get("username", "")
        self.password = (config or {}).get("password", "")
        self.cookie = (config or {}).get("cookie", "")

    def _has_valid_cookie(self) -> bool:
        """检查是否有有效的 Cookie"""
        if not self.cookie:
            return False
        try:
            import requests
            # 尝试访问用户信息接口
            for api in ["/api/user/profile", "/api/user/info"]:
                try:
                    r = requests.get(
                        f"{self.site_url}{api}",
                        headers={
                            "Cookie": self.cookie,
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        },
                        timeout=10,
                    )
                    if r.status_code == 200:
                        return True
                except:
                    continue
            # 回退：检查 Cookie 中是否有认证字段
            auth_keywords = ["auth", "token", "session", "oshwhub", "identity"]
            for item in self.cookie.split(";"):
                item = item.strip()
                if "=" in item:
                    name = item.split("=")[0].strip().lower()
                    for kw in auth_keywords:
                        if kw in name:
                            return True
            return False
        except Exception:
            return False

    def test_connection(self) -> dict:
        """测试连接状态"""
        if self._has_valid_cookie():
            return {"success": True, "status": "✅ Cookie 有效", "logged_in": True}
        if self.username and self.password:
            return {"success": True, "status": "⏳ 已配置，请使用浏览器登录", "logged_in": False, "needs_login": True}
        return {"success": False, "status": "❌ 未配置", "logged_in": False}

    def playwright_login(self) -> dict:
        """调用 Playwright 浏览器登录"""
        from plugins.oshwhub_login import OshwhubPlaywrightLogin
        inst = OshwhubPlaywrightLogin()
        try:
            result = inst.login(self.username, self.password)
            if result.get("logged_in") and result.get("cookies"):
                self.cookie = result["cookies"]
                self.config["cookie"] = result["cookies"]
            return result
        finally:
            inst.close()

    # ─── 签到 ─────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """OSHWHub 不支持自动签到"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────
    def publish(self, article: Article, **kwargs) -> dict:
        """发布项目到立创开源硬件平台"""
        if not self._has_valid_cookie():
            return {"success": False, "error": "Cookie 无效，请先通过 Playwright 登录"}

        try:
            import requests

            # 尝试多个可能的 API 端点
            api_endpoints = [
                "/api/articles",
                "/api/project/publish",
                "/api/v1/projects",
            ]

            payload = {
                "title": article.title,
                "content": article.body or "",
                "introduction": article.summary or (article.body[:200] if article.body else ""),
                "tags": article.tags or kwargs.get("tags", []),
            }

            for api_path in api_endpoints:
                try:
                    resp = requests.post(
                        f"{self.site_url}{api_path}",
                        headers={
                            "Cookie": self.cookie,
                            "Content-Type": "application/json",
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                            "Origin": self.site_url,
                            "Referer": f"{self.site_url}/",
                            "X-Requested-With": "XMLHttpRequest",
                        },
                        json=payload,
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict):
                            item_id = data.get("uuid") or data.get("id") or data.get("projectId") or ""
                            if item_id:
                                return {
                                    "success": True,
                                    "url": f"{self.site_url}/project/{item_id}",
                                    "id": str(item_id),
                                    "error": "",
                                }
                        # 成功但无 ID
                        return {"success": True, "url": f"{self.site_url}/", "id": "", "error": ""}
                    elif resp.status_code != 418:
                        # 非 WAF 拦截的错误
                        try:
                            err_data = resp.json()
                            err_msg = str(err_data.get("message", err_data.get("error", resp.text[:200])))
                        except:
                            err_msg = resp.text[:200]
                        return {"success": False, "error": f"{api_path} → {resp.status_code}: {err_msg}"}
                    # 418：被 WAF 拦截，尝试下一个端点
                except requests.RequestException:
                    continue

            return {"success": False, "error": "所有 API 端点均返回 418（被 WAF 拦截），"
                                                "请使用密码模式 Playwright 登录后 Cookie 再试"}
        except Exception as e:
            return {"success": False, "error": f"发布异常: {e}", "url": "", "id": ""}

    # ─── 撤回 ─────────────────────────────────
    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """OSHWHub 暂不支持撤回"""
        return {"supported": False}

    # ─── 采集项目 ─────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """从 OSHWHub 采集最新项目（探素页/API）"""
        site_url = self.config.get("site_url", "https://oshwhub.com").rstrip("/")
        cookie = self.config.get("cookie", "")
        articles = []

        try:
            import requests
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/125.0.0.0 Safari/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            if cookie:
                domain = site_url.replace("https://", "").split("/")[0]
                for item in cookie.split(";"):
                    item = item.strip()
                    if "=" in item:
                        k, v = item.split("=", 1)
                        session.cookies.set(k.strip(), v.strip(), domain=domain)

            # 尝试 API 方式获取项目列表
            api_paths = [
                "/api/project/list",
                "/api/v1/projects",
                "/api/projects",
                "/api/explore",
                "/api/articles",
            ]
            for api_path in api_paths:
                try:
                    resp = session.get(
                        f"{site_url}{api_path}",
                        timeout=10,
                        headers={"Accept": "application/json",
                                 "Referer": f"{site_url}/explore",
                                 "X-Requested-With": "XMLHttpRequest"}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        items = []
                        if isinstance(data, list):
                            items = data
                        elif isinstance(data, dict):
                            items = (data.get("data", []) or data.get("projects", [])
                                     or data.get("list", []) or data.get("results", [])
                                     or data.get("items", []))
                        for item in items[:20]:
                            if isinstance(item, dict):
                                title = (item.get("title", "") or item.get("name", "")
                                         or item.get("projectName", ""))
                                if not title:
                                    continue
                                article = Article(
                                    title=title,
                                    body=item.get("description", "") or item.get("summary", "")
                                         or item.get("content", ""),
                                    source=self.name,
                                    source_url=f"{site_url}/project/{item.get('id', '')}",
                                    source_id=str(item.get("id", "")),
                                    author=(item.get("author", {}).get("name", "")
                                            if isinstance(item.get("author"), dict)
                                            else item.get("author", "")),
                                    tags=item.get("tags", []),
                                    images=item.get("images", []),
                                    created_at=(item.get("createdAt", "") or
                                                item.get("createTime", "") or
                                                item.get("publishTime", "")),
                                    raw=item,
                                )
                                articles.append(article)
                        if articles:
                            return articles
                except:
                    continue

            # 尝试从探素页面 HTML 解析
            resp = session.get(f"{site_url}/explore", timeout=15)
            # 尝试提取 __NEXT_DATA__
            nd_match = re.search(
                r'<script[^>]*id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>'
                r'(.*?)</script>',
                resp.text, re.DOTALL
            )
            if nd_match:
                try:
                    nd = json.loads(nd_match.group(1))
                    props = nd.get("props", {}).get("pageProps", {})
                    projects = (props.get("projects", []) or props.get("list", [])
                                or props.get("data", {}).get("projects", []))
                    for proj in projects[:20]:
                        if isinstance(proj, dict):
                            title = proj.get("title", "") or proj.get("name", "")
                            if title:
                                articles.append(Article(
                                    title=title,
                                    source=self.name,
                                    source_url=f"{site_url}/project/{proj.get('id', '')}",
                                    source_id=str(proj.get("id", "")),
                                    raw=proj,
                                ))
                except:
                    pass

            if not articles:
                # 从 HTML 提取项目卡片
                for m in re.finditer(
                    r'<a[^>]*href="/(?:project|explore)/(\d+)"[^>]*>([^<]+)</a>',
                    resp.text
                ):
                    title = m.group(2).strip()
                    pid = m.group(1)
                    if title and len(title) > 3:
                        articles.append(Article(
                            title=title,
                            source=self.name,
                            source_url=f"{site_url}/project/{pid}",
                            source_id=pid,
                            raw={"source": "html_parse"},
                        ))

            return articles[:20]
        except Exception:
            return []

    # ─── 采集回复 ─────────────────────────────
    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        return []

    # ─── 读项目详情 ───────────────────────────
    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """获取单篇项目的详细内容"""
        if not thread_id:
            return None
        try:
            import requests
            site_url = self.config.get("site_url", "https://oshwhub.com").rstrip("/")
            project_url = f"{site_url}/project/{thread_id}"
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            cookie = self.config.get("cookie", "")
            if cookie:
                domain = site_url.replace("https://", "").split("/")[0]
                for item in cookie.split(";"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        session.cookies.set(k.strip(), v.strip(), domain=domain)

            resp = session.get(project_url, timeout=15)

            # 尝试 __NEXT_DATA__
            nd_match = re.search(
                r'<script[^>]*id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>(.*?)</script>',
                resp.text, re.DOTALL
            )
            if nd_match:
                try:
                    nd = json.loads(nd_match.group(1))
                    props = nd.get("props", {}).get("pageProps", {})
                    project = props.get("project", props.get("data", props))
                    if project:
                        title = project.get("title", "") or project.get("name", "")
                        body = (project.get("content", "") or project.get("description", "")
                                or project.get("body", ""))
                        author = ""
                        ad = project.get("author", {})
                        if isinstance(ad, dict):
                            author = ad.get("name", ad.get("username", ""))
                        elif isinstance(ad, str):
                            author = ad
                        tags = project.get("tags", [])
                        if isinstance(tags, str):
                            tags = [t.strip() for t in tags.split(",") if t.strip()]
                        return Article(
                            title=title, body=body, source=self.name,
                            source_url=project_url, source_id=thread_id,
                            author=author, tags=tags,
                            created_at=(project.get("createdAt", "") or
                                        project.get("createTime", "")),
                            raw=project,
                        )
                except:
                    pass

            # 尝试 API
            for api in [f"/api/project/detail?id={thread_id}", f"/api/articles/{thread_id}"]:
                try:
                    r = session.get(f"{site_url}{api}", timeout=10,
                                    headers={"Accept": "application/json"})
                    if r.status_code == 200:
                        data = r.json()
                        if isinstance(data, dict):
                            proj = data.get("data", data)
                            title = proj.get("title", "") or proj.get("name", "")
                            if title:
                                return Article(
                                    title=title,
                                    body=proj.get("content", "") or proj.get("description", ""),
                                    source=self.name, source_url=project_url,
                                    source_id=thread_id, raw=proj,
                                )
                except:
                    continue

            # 回退：从 HTML 提取标题
            title_m = re.search(r'<title>(.*?)</title>', resp.text)
            title = title_m.group(1).strip() if title_m else ""
            if title and "开源硬件" not in title:
                return Article(title=title, source=self.name,
                               source_url=project_url, source_id=thread_id)

            return None
        except Exception:
            return None

    # ─── 回复评论 ─────────────────────────────
    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        return {"supported": False}

    # ─── 逛平台 ───────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """浏览 OSHWHub 探索页，获取热门/最新开源项目"""
        try:
            import requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            if self.cookie:
                headers["Cookie"] = self.cookie

            resp = requests.get(f"{self.site_url}/explore", headers=headers, timeout=10)
            projects = []
            # 尝试 JSON API
            api_headers = dict(headers)
            api_headers["Accept"] = "application/json"
            for api in ["/api/projects", "/api/v1/projects"]:
                try:
                    r = requests.get(f"{self.site_url}{api}", headers=api_headers, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        items = data
                        if isinstance(data, dict):
                            items = data.get("data", data.get("results", data.get("projects", [])))
                        if isinstance(items, list):
                            for p in items[:30]:
                                title = p.get("title", p.get("name", ""))
                                if title:
                                    projects.append({
                                        "title": title,
                                        "url": f"{self.site_url}/{p.get('user', '')}/{p.get('id', '')}",
                                        "author": p.get("user", p.get("author", "")),
                                        "summary": p.get("description", "")[:100],
                                    })
                            break
                except:
                    continue

            # 回退：从 HTML 提取
            if not projects:
                for m in re.finditer(
                    r'<a[^>]*href="/([^"]+)"[^>]*>(.*?)</a>',
                    resp.text, re.DOTALL
                ):
                    url = m.group(1)
                    title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                    if title and len(title) > 3 and "/" in url and not url.startswith("http"):
                        projects.append({"title": title, "url": f"{self.site_url}/{url}"})

            return {
                "supported": True, "total": len(projects),
                "filtered": 0, "new_saved": 0,
                "projects": projects[:30],
            }
        except Exception as e:
            return {"supported": True, "total": 0, "error": str(e)}

    # ─── 部署 ─────────────────────────────────
    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        return {"supported": False}
