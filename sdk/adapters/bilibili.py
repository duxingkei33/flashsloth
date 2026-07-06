"""
Bilibili (哔哩哔哩 / bilibili.com) 平台适配器

基于 Bilibili 开放 API + Cookie 认证方式访问。

能力清单：
  - sign_in()             每日签到（不支持）
  - publish()             发布专栏文章 ✅（基于 Bilibili 专栏 API）
  - retract()             撤回文章（不支持）
  - fetch_posts()         采集专栏列表 ✅
  - fetch_replies()       采集评论（不支持）
  - fetch_thread_detail() 获取专栏详情 ✅
  - reply_comment()       回复评论（不支持）
  - browse_forum()        逛 B站（不支持）
  - deploy()              部署（不支持）

认证方式：
  使用 Bilibili Cookie 认证（SESSDATA + bili_jct + DedeUserID）
  从浏览器 F12 → Application → Cookies → bilibili.com 复制

Bilibili API 文档参考：
  https://api.bilibili.com/x/web-interface/nav  — 登录状态检测
  https://api.bilibili.com/x/article/            — 专栏相关 API
"""
from typing import Optional
import re, json, time, os

from ..adapter import PlatformAdapter, register, Article, Comment


# Bilibili API 基础 URL
BAPI = "https://api.bilibili.com"
BWEB = "https://www.bilibili.com"


@register
class BilibiliAdapter(PlatformAdapter):
    name = "bilibili"
    display_name = "Bilibili"
    site_url = "https://www.bilibili.com"
    version = "1.0.0"
    description = "哔哩哔哩 (Bilibili) — 中国年轻一代的潮流文化社区"
    icon = "📺"

    config_fields = [
        {
            "key": "cookie",
            "label": "Cookie（SESSDATA + bili_jct）",
            "type": "password",
            "required": True,
            "placeholder": "登录后从浏览器 F12 复制完整 Cookie",
        },
        {
            "key": "default_category",
            "label": "默认专栏分类",
            "type": "select",
            "required": False,
            "options": [
                {"value": "0", "label": "默认分类"},
                {"value": "1", "label": "动画"},
                {"value": "2", "label": "游戏"},
                {"value": "3", "label": "科技"},
                {"value": "4", "label": "生活"},
                {"value": "5", "label": "娱乐"},
                {"value": "6", "label": "影视"},
            ],
            "placeholder": "选择专栏发布时的默认分类",
        },
        {
            "key": "uid",
            "label": "Bilibili UID",
            "type": "text",
            "required": False,
            "placeholder": "B站用户 ID（数字）",
        },
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        cfg = config or {}
        self.cookie = cfg.get("cookie", "")
        self.default_category = cfg.get("default_category", "0")
        self.uid = cfg.get("uid", "")
        # 从 Cookie 中提取认证字段
        self.sessdata = self._extract_cookie("SESSDATA")
        self.bili_jct = self._extract_cookie("bili_jct")
        self.dede_user_id = self._extract_cookie("DedeUserID")

    def _extract_cookie(self, key: str) -> str:
        """从 Cookie 字符串中提取指定 key 的值"""
        if not self.cookie:
            return ""
        pattern = re.compile(rf'(?:^|;\s*){re.escape(key)}=([^;]+)')
        m = pattern.search(self.cookie)
        return m.group(1) if m else ""

    def _headers(self) -> dict:
        """构造通用请求头"""
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Cookie": self.cookie,
            "Referer": "https://www.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    # ─── 签到 ─────────────────────────────────

    def sign_in(self, check_only: bool = False) -> dict:
        """Bilibili 无公开签到 API"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────

    def publish(self, article: Article, **kwargs) -> dict:
        """发布专栏文章到 Bilibili

        使用 Bilibili 专栏 API 创建/发布文章。
        需要 Cookie 中包含有效的 SESSDATA + bili_jct。

        kwargs 支持:
            category: int        — 分类 ID（覆盖默认配置）
            tags: list           — 文章标签
            cover: str           — 封面图 URL
            original: int        — 是否原创 (1=原创, 0=转载, 默认1)
            save_as_draft: bool  — 仅存草稿不发布 (默认 False)

        返回: {"success": bool, "url": str, "id": str, "error": str}
        """
        if not self._is_authenticated():
            return {
                "success": False, "url": "", "id": "",
                "error": "Cookie 缺失必要字段（需要 SESSDATA + bili_jct）",
            }

        title = article.title.strip()
        if not title:
            return {
                "success": False, "url": "", "id": "",
                "error": "标题不能为空",
            }

        body = article.body
        if not body:
            return {
                "success": False, "url": "", "id": "",
                "error": "文章内容不能为空",
            }

        try:
            import requests as req

            # ── 第1步：创建草稿 ──
            category = kwargs.get("category", int(self.default_category))
            tags = kwargs.get("tags", article.tags or [])
            cover = kwargs.get("cover", "")
            original = kwargs.get("original", 1)

            # 将 Markdown 内容转为 Bilibili 兼容 HTML
            content_html = self._body_to_bilibili_html(body, article.images)

            draft_data = {
                "category": category,
                "title": title,
                "content": content_html,
                "summary": article.summary or title[:80],
                "tags": ",".join(tags) if tags else "",
                "cover": cover,
                "original": original,
            }

            # Bilibili 专栏 API 使用 POST form-data
            headers = self._headers()
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

            # 添加 CSRF token
            if self.bili_jct:
                draft_data["csrf"] = self.bili_jct

            resp = req.post(
                f"{BAPI}/x/article/creative/draft/addition",
                data=draft_data,
                headers=headers,
                timeout=30,
            )

            result = resp.json()
            if result.get("code") != 0:
                return {
                    "success": False, "url": "", "id": "",
                    "error": f"创建草稿失败: {result.get('message', '未知错误')} (code={result.get('code')})",
                }

            draft_id = result.get("data", {}).get("article_id", "")
            if not draft_id:
                draft_id = result.get("data", {}).get("draft_id", "")

            if not draft_id:
                return {
                    "success": False, "url": "", "id": "",
                    "error": "创建草稿成功但未返回 ID",
                }

            # ── 如果只存草稿，不发布 ──
            if kwargs.get("save_as_draft", False):
                return {
                    "success": True,
                    "url": "",
                    "id": str(draft_id),
                    "error": "",
                    "message": f"草稿已保存 (draft_id={draft_id})",
                }

            # ── 第2步：发布草稿 ──
            submit_data = {
                "draft_id": draft_id,
                "category": category,
            }
            if self.bili_jct:
                submit_data["csrf"] = self.bili_jct

            submit_resp = req.post(
                f"{BAPI}/x/article/creative/draft/submit",
                data=submit_data,
                headers=headers,
                timeout=30,
            )

            submit_result = submit_resp.json()
            if submit_result.get("code") != 0:
                return {
                    "success": False, "url": "", "id": draft_id,
                    "error": f"发布草稿失败: {submit_result.get('message', '未知错误')} (code={submit_result.get('code')})",
                }

            article_id = submit_result.get("data", {}).get("article_id", draft_id)
            article_url = f"{BWEB}/read/cv{article_id}/"

            return {
                "success": True,
                "url": article_url,
                "id": str(article_id),
                "error": "",
                "message": f"cv{article_id}",
            }

        except ImportError:
            return {
                "success": False, "url": "", "id": "",
                "error": "缺少 requests 库，请安装: pip install requests",
            }
        except Exception as e:
            return {
                "success": False, "url": "", "id": "",
                "error": f"发布异常: {e}",
            }

    def _body_to_bilibili_html(self, body: str, images: list = None) -> str:
        """将正文转为 Bilibili 专栏兼容的 HTML

        Bilibili 专栏编辑使用富文本，支持基本的 HTML 标签。
        """
        text = body

        # Markdown 标题
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)

        # 粗体/斜体/行内代码
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

        # 图片
        if images:
            for img_url in images:
                img_tag = f'<img src="{img_url}" />'
                # 替换 Markdown 图片语法
                text = re.sub(
                    rf'!\[.*?\]\({re.escape(img_url)}\)',
                    img_tag,
                    text,
                )

        # 通用 Markdown 图片（未匹配到的）
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" />', text)

        # 链接
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

        # 段落包裹
        parts = []
        for para in text.split('\n\n'):
            para = para.strip()
            if not para:
                continue
            if not re.match(r'^\s*<', para):
                para = f'<p>{para}</p>'
            parts.append(para)
        text = '\n'.join(parts)

        return text.strip()

    def upload_image(self, local_path: str) -> dict:
        """上传图片到 Bilibili 图床

        Bilibili 专栏图片上传 API:
        POST https://api.bilibili.com/x/article/creative/image/upload
        multipart/form-data, 需要 Cookie + CSRF

        返回: {"success": bool, "url": str, "error": str}
        """
        if not self._is_authenticated():
            return {"success": False, "url": "", "error": "Cookie 无效或未配置"}

        if not local_path or not os.path.isfile(local_path):
            return {"success": False, "url": "", "error": f"文件不存在: {local_path}"}

        try:
            import requests as req

            # 检查文件大小 (Bilibili 限制推测 10MB)
            file_size = os.path.getsize(local_path)
            if file_size > 10 * 1024 * 1024:
                return {"success": False, "url": "", "error": f"文件过大 ({file_size / 1024 / 1024:.1f}MB > 10MB)"}

            headers = self._headers()
            # Bilibili 图片上传不需要 Content-Type header (requests 自动设置)

            with open(local_path, "rb") as f:
                files = {
                    "file": (os.path.basename(local_path), f, "image/jpeg" if local_path.lower().endswith((".jpg", ".jpeg")) else "image/png"),
                    "csrf": (None, self.bili_jct),
                }
                resp = req.post(
                    f"{BAPI}/x/article/creative/image/upload",
                    files=files,
                    headers=headers,
                    timeout=30,
                )

            result = resp.json()
            if result.get("code") == 0:
                img_url = result.get("data", {}).get("url", "")
                if img_url:
                    return {"success": True, "url": img_url, "error": ""}

            return {
                "success": False, "url": "",
                "error": f"上传失败: {result.get('message', '未知错误')} (code={result.get('code')})",
            }

        except ImportError:
            return {"success": False, "url": "", "error": "缺少 requests 库"}
        except Exception as e:
            return {"success": False, "url": "", "error": f"上传异常: {e}"}

    # ─── 撤回 ─────────────────────────────────

    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """Bilibili 专栏暂不支持通过 API 撤回"""
        return {"supported": False}

    # ─── 采集帖子 ─────────────────────────────

    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """从 Bilibili 采集专栏文章列表

        需要配置 uid。按时间倒序返回最近发布的专栏。
        """
        if not self.uid:
            return []

        target_uid = kwargs.get("uid", self.uid)
        if not target_uid:
            return []

        try:
            import requests as req

            articles = []
            for page in range(1, max_pages + 1):
                resp = req.get(
                    f"{BAPI}/x/space/article",
                    params={
                        "mid": target_uid,
                        "pn": page,
                        "ps": 30,
                        "order": "publish_time",
                    },
                    headers=self._headers(),
                    timeout=15,
                )

                result = resp.json()
                if result.get("code") != 0:
                    break

                data_list = result.get("data", {}).get("articles", [])
                if not data_list:
                    break

                for item in data_list:
                    article = Article(
                        title=item.get("title", ""),
                        body=item.get("content", ""),
                        summary=item.get("summary", "") or item.get("title", "")[:80],
                        tags=[t.get("name", "") for t in item.get("tags", [])],
                        source="bilibili",
                        source_url=f"{BWEB}/read/cv{item.get('id', '')}/",
                        source_id=str(item.get("id", "")),
                        author=item.get("author", {}).get("name", ""),
                        images=[item.get("image_urls", [])] if item.get("image_urls") else [],
                    )
                    articles.append(article)

                if len(data_list) < 30:
                    break

            return articles

        except Exception:
            return []

    # ─── 采集回复 ─────────────────────────────

    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """Bilibili 评论采集暂不支持"""
        return []

    # ─── 读帖详情 ─────────────────────────────

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """获取 Bilibili 专栏文章详情

        thread_id 格式: 数字（不带 cv 前缀）或 "cv12345"
        """
        if not thread_id:
            return None

        # 去除 cv 前缀
        raw_id = thread_id.replace("cv", "").strip()
        if not raw_id.isdigit():
            return None

        try:
            import requests as req

            resp = req.get(
                f"{BAPI}/x/article/viewinfo",
                params={"id": raw_id},
                headers=self._headers(),
                timeout=15,
            )

            result = resp.json()
            if result.get("code") != 0:
                return None

            data = result.get("data", {})
            if not data:
                return None

            title = data.get("title", "")
            content = data.get("content", "")
            summary = data.get("summary", "") or title[:80]

            # 提取标签
            tags = []
            for t in data.get("tags", []):
                if isinstance(t, dict):
                    tags.append(t.get("name", ""))
                elif isinstance(t, str):
                    tags.append(t)

            # 提取作者
            author_name = ""
            author_info = data.get("author", {})
            if isinstance(author_info, dict):
                author_name = author_info.get("name", "")

            # 提取封面/图片
            images = []
            image_urls = data.get("image_urls", [])
            if isinstance(image_urls, list):
                images = image_urls
            else:
                cover = data.get("cover", "")
                if cover:
                    images = [cover]

            return Article(
                title=title,
                body=content,
                summary=summary,
                tags=tags,
                source="bilibili",
                source_url=f"{BWEB}/read/cv{raw_id}/",
                source_id=raw_id,
                author=author_name,
                images=images,
            )

        except Exception:
            return None

    # ─── 回复评论 ─────────────────────────────

    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """Bilibili 暂不支持自动回复评论"""
        return {"supported": False}

    # ─── 逛论坛 ───────────────────────────────

    def browse_forum(self, **kwargs) -> dict:
        """Bilibili 暂不支持自动浏览推荐内容"""
        return {"supported": False}

    # ─── 部署 ─────────────────────────────────

    def deploy(self, **kwargs) -> dict:
        """Bilibili 不涉及站点部署"""
        return {"supported": False}

    # ─── 工具方法 ─────────────────────────────

    def test_connection(self) -> dict:
        """测试 Bilibili Cookie 是否有效"""
        if not self.cookie:
            return {
                "success": False, "error": "Cookie 为空",
                "status": "无 Cookie",
            }
        if not self._is_authenticated():
            return {
                "success": False,
                "error": "Cookie 缺少必要字段（需要 SESSDATA + bili_jct）",
                "status": "Cookie 格式错误",
            }

        try:
            import requests as req

            resp = req.get(
                f"{BAPI}/x/web-interface/nav",
                headers=self._headers(),
                timeout=10,
            )

            result = resp.json()
            if result.get("code") == 0:
                data = result.get("data", {})
                is_login = data.get("isLogin", False)
                if is_login:
                    uname = data.get("uname", "") or data.get("userInfo", {}).get("uname", "")
                    return {
                        "success": True,
                        "error": "",
                        "status": f"✅ 已登录 — {uname}",
                        "uid": data.get("mid", ""),
                    }
                return {
                    "success": False,
                    "error": "Cookie 无效或已过期",
                    "status": "Cookie 过期",
                }
            elif result.get("code") == -101:
                return {
                    "success": False,
                    "error": "Cookie 无效（-101 未登录）",
                    "status": "未登录",
                }
            else:
                return {
                    "success": False,
                    "error": f"API 返回错误: {result.get('message', '未知')}",
                    "status": "验证失败",
                }

        except ImportError:
            return {
                "success": False, "error": "缺少 requests 库",
                "status": "依赖缺失",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"连接异常: {e}",
                "status": "连接失败",
            }

    def _is_authenticated(self) -> bool:
        """检查是否已配置基本认证信息"""
        return bool(self.sessdata) and bool(self.bili_jct)

    def get_user_info(self) -> dict:
        """获取当前登录用户信息"""
        if not self.cookie:
            return {"success": False, "error": "Cookie 为空"}

        try:
            import requests as req

            resp = req.get(
                f"{BAPI}/x/web-interface/nav",
                headers=self._headers(),
                timeout=10,
            )

            result = resp.json()
            if result.get("code") == 0:
                data = result.get("data", {})
                return {
                    "success": True,
                    "is_login": data.get("isLogin", False),
                    "uid": data.get("mid", ""),
                    "username": data.get("uname", ""),
                    "level": data.get("level_info", {}).get("current_level", 0),
                    "avatar": data.get("face", ""),
                }
            return {
                "success": False,
                "error": result.get("message", "未知错误"),
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def get_raw_content(self, cvid: str) -> Optional[str]:
        """获取专栏原始 Markdown/HTML 内容"""
        article = self.fetch_thread_detail(cvid)
        if article:
            return article.body
        return None
