"""
Bilibili (哔哩哔哩) 专栏 Publisher — 发布专栏文章到 Bilibili

基于 Bilibili 开放 API + Cookie 认证。

认证方式：
  使用 Bilibili Cookie 认证（SESSDATA + bili_jct + DedeUserID）
  从浏览器 F12 → Application → Cookies → bilibili.com 复制

发布流程：
  1. 创建草稿 (draft/addition)
  2. 提交发布 (draft/submit)

依赖：
  pip install requests

API 文档：
  https://api.bilibili.com/x/web-interface/nav              — 登录状态检测
  https://api.bilibili.com/x/article/creative/draft/addition — 创建草稿
  https://api.bilibili.com/x/article/creative/draft/submit   — 发布草稿
"""
from typing import Optional
import re, json, os
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


BAPI = "https://api.bilibili.com"
BWEB = "https://www.bilibili.com"


def _extract_cookie_value(cookie_str: str, key: str) -> str:
    """从 Cookie 字符串中提取指定 key 的值"""
    if not cookie_str:
        return ""
    pattern = re.compile(rf'(?:^|;\s*){re.escape(key)}=([^;]+)')
    m = pattern.search(cookie_str)
    return m.group(1) if m else ""


@register
class BilibiliPublisher(Publisher):
    name = "bilibili"
    display_name = "Bilibili 专栏"
    login_methods = [
        {"method": "password", "label": "账号密码登录", "icon": "🔑", "priority": 1,
         "fields": ["username", "password"],
         "description": "输入 Bilibili 用户名和密码，Playwright 浏览器自动登录"},
        {"method": "qrcode", "label": "📱 扫码登录", "icon": "📱", "priority": 2,
         "fields": [],
         "description": "打开 Bilibili 登录页截图，用手机 App 扫码后自动捕获 Cookie"},
        {"method": "cookie", "label": "Cookie 粘贴（备选）", "icon": "🍪", "priority": 99,
         "fields": ["cookie"],
         "description": "登录 Bilibili 后从浏览器 F12 复制 Cookie"},
    ]
    config_fields = [
        {"key": "username", "label": "用户名/邮箱", "type": "text", "required": False, "default": ""},
        {"key": "password", "label": "密码", "type": "password", "required": False, "default": ""},
        {
            "key": "cookie",
            "label": "Cookie（备选）",
            "type": "password",
            "required": False,
            "placeholder": "登录后从浏览器 F12 → Application → Cookies → bilibili.com 复制",
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
    ]

    capabilities = ["publish", "test_connection", "upload_image"]
    supports_draft = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie = config.get("cookie", "")
        self.default_category = config.get("default_category", "0")
        self.sessdata = _extract_cookie_value(self.cookie, "SESSDATA")
        self.bili_jct = _extract_cookie_value(self.cookie, "bili_jct")

    def _headers(self) -> dict:
        """构造请求头"""
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

    def _is_auth_valid(self) -> bool:
        """检查 Cookie 中是否含有必要认证字段"""
        return bool(self.sessdata) and bool(self.bili_jct)

    def _body_to_html(self, body: str, images: list = None) -> str:
        """将 Markdown 正文转为 Bilibili 专栏兼容的 HTML"""
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
                text = re.sub(
                    rf'!\[.*?\]\({re.escape(img_url)}\)',
                    f'<img src="{img_url}" />',
                    text,
                )

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

    def test_connection(self) -> dict:
        """测试 Bilibili Cookie 是否有效"""
        if not self.cookie:
            return {"success": False, "error": "Cookie 为空", "status": "无 Cookie"}
        if not self._is_auth_valid():
            return {
                "success": False,
                "error": "Cookie 缺少 SESSDATA 或 bili_jct",
                "status": "Cookie 格式错误",
            }

        try:
            import requests

            resp = requests.get(
                f"{BAPI}/x/web-interface/nav",
                headers=self._headers(),
                timeout=10,
            )
            result = resp.json()
            if result.get("code") == 0 and result.get("data", {}).get("isLogin"):
                uname = result.get("data", {}).get("uname", "")
                return {
                    "success": True, "error": "",
                    "status": f"✅ 已登录 — {uname}",
                }
            return {
                "success": False,
                "error": "Cookie 无效或已过期",
                "status": "未登录",
            }
        except ImportError:
            return {"success": False, "error": "缺少 requests 库", "status": "依赖缺失"}
        except Exception as e:
            return {"success": False, "error": f"连接异常: {e}", "status": "连接失败"}

    def publish(self, article: Article, **kwargs) -> dict:
        """发布专栏文章到 Bilibili

        两步流程：
          1. 创建草稿 (draft/addition)
          2. 提交发布 (draft/submit)

        返回: {"success": bool, "url": str, "id": str, "error": str, "message": str}
        """
        if not self.cookie:
            return {
                "success": False, "url": "", "id": "",
                "error": "请先在配置中填写 Bilibili Cookie",
            }
        if not self._is_auth_valid():
            return {
                "success": False, "url": "", "id": "",
                "error": "Cookie 格式不正确，需要包含 SESSDATA 和 bili_jct",
            }

        title = article.title.strip()
        if not title:
            return {"success": False, "url": "", "id": "", "error": "标题不能为空"}

        body = article.body or ""
        if not body.strip():
            return {"success": False, "url": "", "id": "", "error": "文章内容不能为空"}

        try:
            import requests

            # ── 参数 ──
            category = kwargs.get("category", int(self.default_category))
            tags = kwargs.get("tags", article.tags or [])
            cover = kwargs.get("cover", "")
            original = kwargs.get("original", 1)

            content_html = self._body_to_html(body, article.images)

            # ── 第1步：创建草稿 ──
            draft_data = {
                "category": category,
                "title": title,
                "content": content_html,
                "summary": article.summary or title[:80],
                "tags": ",".join(tags) if tags else "",
                "cover": cover,
                "original": original,
            }
            if self.bili_jct:
                draft_data["csrf"] = self.bili_jct

            headers = self._headers()
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

            resp = requests.post(
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

            draft_id = result.get("data", {}).get("article_id", "") or \
                       result.get("data", {}).get("draft_id", "")

            if not draft_id:
                return {
                    "success": False, "url": "", "id": "",
                    "error": "创建草稿成功但未获取到文章 ID",
                }

            # ── 如果只存草稿，不发布 ──
            save_as_draft = kwargs.get("save_as_draft", False)
            if save_as_draft:
                return {
                    "success": True,
                    "url": "",
                    "id": str(draft_id),
                    "error": "",
                    "message": f"草稿已保存 (draft_id={draft_id})",
                }

            # ── 第2步：提交发布 ──
            submit_data = {"draft_id": draft_id, "category": category}
            if self.bili_jct:
                submit_data["csrf"] = self.bili_jct

            submit_resp = requests.post(
                f"{BAPI}/x/article/creative/draft/submit",
                data=submit_data,
                headers=headers,
                timeout=30,
            )

            submit_result = submit_resp.json()
            if submit_result.get("code") != 0:
                error_msg = submit_result.get("message", "未知错误")
                # 某些错误码（如 110011）表示草稿已发布过，也视为成功
                if submit_result.get("code") in (110011,):
                    article_url = f"{BWEB}/read/cv{draft_id}/"
                    return {
                        "success": True,
                        "url": article_url,
                        "id": str(draft_id),
                        "error": "",
                        "message": f"cv{draft_id}（草稿可能已发布过）",
                    }
                return {
                    "success": False, "url": "", "id": draft_id,
                    "error": f"发布草稿失败: {error_msg} (code={submit_result.get('code')})",
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
                "error": "缺少 requests 库，请执行: pip install requests",
            }
        except Exception as e:
            return {
                "success": False, "url": "", "id": "",
                "error": f"发布异常: {e}",
            }

    def upload_image(self, local_path: str) -> dict:
        """上传图片到 Bilibili 图床

        使用 Bilibili 专栏图片上传 API:
        POST https://api.bilibili.com/x/article/creative/image/upload

        返回: {"success": bool, "url": str, "error": str}
        """
        if not self.cookie or not self._is_auth_valid():
            return {"success": False, "url": "", "error": "Cookie 无效或未配置"}

        if not local_path or not os.path.isfile(local_path):
            return {"success": False, "url": "", "error": f"文件不存在: {local_path}"}

        try:
            import requests

            file_size = os.path.getsize(local_path)
            if file_size > 10 * 1024 * 1024:
                return {
                    "success": False, "url": "",
                    "error": f"文件过大 ({file_size / 1024 / 1024:.1f}MB > 10MB)",
                }

            headers = self._headers()
            with open(local_path, "rb") as f:
                files = {
                    "file": (
                        os.path.basename(local_path),
                        f,
                        "image/jpeg" if local_path.lower().endswith((".jpg", ".jpeg")) else "image/png",
                    ),
                    "csrf": (None, self.bili_jct),
                }
                resp = requests.post(
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

    def retract(self, article: Article, publish_log: dict = None) -> dict:
        """Bilibili 专栏暂不支持通过 API 撤回"""
        return {
            "success": True,
            "error": "",
            "message": "Bilibili 不支持自动撤回，请手动到 bilibili.com 删除",
        }

    def validate_config(self) -> list[str]:
        missing = []
        if not self.cookie:
            missing.append("cookie")
        return missing
