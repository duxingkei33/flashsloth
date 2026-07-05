"""
哔哩哔哩 Publisher — 发布专栏文章

使用 Cookie 方式登录 B站，发布专栏文章。
视频投稿功能为预留状态（开发中）。
"""
import json, re
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class BilibiliPublisher(Publisher):
    name = "bilibili"
    display_name = "哔哩哔哩"
    config_fields = [
        {"key": "site_url", "label": "网站地址", "type": "text", "required": True,
         "default": "https://www.bilibili.com", "placeholder": "https://www.bilibili.com"},
        {"key": "username", "label": "B站用户名", "type": "text", "required": False,
         "placeholder": "B站登录用户名"},
        {"key": "password", "label": "密码", "type": "password", "required": False,
         "placeholder": "B站登录密码"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": False,
         "placeholder": "登录后从浏览器 F12 复制 Cookie"},
    ]

    API_BASE = "https://api.bilibili.com"
    ARTICLE_API = "https://api.bilibili.com/x/article"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = self.config
        self.site_url = cfg.get("site_url", "https://www.bilibili.com").rstrip("/")
        self.username = cfg.get("username", "")
        self.password = cfg.get("password", "")
        self.cookie = cfg.get("cookie", "")
        self._session = self._build_session() if self.cookie else None

    def _build_session(self):
        import requests
        s = requests.Session()
        # 解析 cookie 字符串
        for item in self.cookie.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                s.cookies.set(k.strip(), v.strip())
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        })
        return s

    def publish(self, article: Article, **kwargs) -> dict:
        """
        发布专栏文章到 B站。
        使用 bilibili 专栏 API (x/article/creative/draft/posts)。
        """
        if not self.cookie:
            return {"success": False, "error": "未配置 Cookie，请先登录获取 Cookie"}

        if not self._session:
            self._session = self._build_session()

        title = article.title
        content = article.body or article.content or ""

        # B站专栏内容需要转为纯文本 + 简单 HTML
        # 这里做基础转换
        text_content = self._convert_to_bilibili_format(content)

        try:
            # Step 1: 获取用户信息（验证 Cookie）
            user_resp = self._session.get(
                f"{self.API_BASE}/x/space/wbi/acc/info",
                params={"mid": 0},
                timeout=10,
            )
            if not user_resp.ok:
                return {"success": False, "error": "Cookie 无效或已过期，请重新登录"}
            user_data = user_resp.json()
            if user_data.get("code") != 0:
                return {"success": False, "error": f"Cookie 验证失败: {user_data.get('message', '未知错误')}"}

            # Step 2: 发布专栏文章
            # B站专栏发布 API — 需要 csrf token
            csrf = self._get_csrf()
            if not csrf:
                return {"success": False, "error": "无法获取 CSRF Token，Cookie 可能不完整"}

            pub_resp = self._session.post(
                f"{self.API_BASE}/x/article/creative/draft/posts",
                data={
                    "title": title,
                    "content": text_content,
                    "category": self._detect_category(title, content),
                    "list_id": 0,
                    "original": 1,
                    "csrf": csrf,
                },
                timeout=30,
            )
            data = pub_resp.json()
            if data.get("code") == 0:
                article_id = data.get("data", {}).get("article_id", "")
                url = f"https://www.bilibili.com/read/cv{article_id}" if article_id else ""
                return {"success": True, "url": url, "id": str(article_id), "error": ""}
            else:
                return {"success": False, "error": f"发布失败: {data.get('message', str(data))}"}

        except Exception as e:
            return {"success": False, "error": f"发布异常: {e}"}

    def publish_video(self, article: Article, **kwargs) -> dict:
        """
        【预留】视频投稿功能 — 开发中
        """
        return {
            "success": False,
            "error": "视频投稿功能开发中（预留），将在后续版本中实现",
        }

    def _get_csrf(self) -> str:
        """从 Cookie 中提取 bili_jct（CSRF Token）"""
        if not self._session:
            return ""
        for cookie in self._session.cookies:
            if cookie.name == "bili_jct":
                return cookie.value
        return ""

    def _convert_to_bilibili_format(self, text: str) -> str:
        """将 Markdown 风格的文本转为 B站专栏格式"""
        # 基础转换：移除 markdown 标记，保留基本格式
        text = re.sub(r'#{1,6}\s+', '', text)  # 标题标记
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # 加粗
        text = re.sub(r'\*(.+?)\*', r'\1', text)  # 斜体
        text = re.sub(r'!\[.*?\]\(.*?\)', '[图片]', text)  # 图片
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)  # 链接
        text = re.sub(r'```[\s\S]*?```', '[代码块]', text)  # 代码块
        text = re.sub(r'`(.+?)`', r'\1', text)  # 行内代码
        return text.strip()

    def _detect_category(self, title: str, content: str) -> int:
        """简单检测专栏分类（B站分类ID）"""
        # 默认：生活（4）
        return 4

    def retract(self, article: Article, publish_log: dict = None) -> dict:
        """B站暂不支持自动撤回文章"""
        return {"success": False, "error": "B站暂不支持自动撤回文章，请手动在B站后台操作"}
