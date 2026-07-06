"""
知乎 Publisher — Playwright 浏览器自动化

知乎专栏 (zhuanlan.zhihu.com) 发布器，使用 Playwright 模拟浏览器操作。
支持 Cookie 登录、存草稿、发布、图片上传。

当前编辑器已知路由：
- https://zhuanlan.zhihu.com/write          — 写新文章
- https://zhuanlan.zhihu.com/p/{id}/edit    — 编辑已有文章

⚠️ 知乎前端频繁改版，选择器可能失效，维护成本较高。
"""
import re, json, os, logging
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

EDITOR_URL = "https://zhuanlan.zhihu.com/write"
ZHIHU_DOMAIN = ".zhihu.com"


def _parse_cookies(cookie_str: str) -> list:
    """将 Cookie 字符串解析为 Playwright 可接受的格式"""
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        cookies.append({"name": n.strip(), "value": v.strip(),
                        "domain": ZHIHU_DOMAIN, "path": "/"})
    return cookies


@register
class ZhihuPublisher(Publisher):
    name = "zhihu"
    display_name = "知乎"

    PLATFORM_LIMITS = {
        "zhihu.com": {
            "max_title_length": 200,
            "min_title_length": 1,
            "supports_draft": True,
            "supports_schedule": False,
            "supports_cover": True,
            "supports_tags": False,
            "article_types": ["original"],
            "image_upload": "playwright",
        }
    }

    login_methods = [
        {"method": "cookie", "label": "Cookie 粘贴", "icon": "🍪", "priority": 1,
         "fields": ["cookie"],
         "description": "登录知乎后从浏览器 F12 → Application → Cookies → zhihu.com 复制"},
    ]
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "知乎全站 Cookie（从 F12 复制）"},
    ]
    supports_draft = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.logger = logging.getLogger(f"publisher.{self.name}")

    def _cookies(self):
        return _parse_cookies(self.cookie_str) if self.cookie_str else []

    def test_connection(self) -> dict:
        """测试 Cookie 有效性"""
        if not self.cookie_str:
            return {"success": False, "error": "未配置 Cookie"}
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, args=[
                    '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                ])
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080}, locale="zh-CN",
                )
                ctx.add_cookies(self._cookies())
                page = ctx.new_page()
                page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                # 检测是否未登录——知乎跳登录页时 URL 含 signin 或 login
                redirected = "signin" in page.url.lower() or "login" in page.url.lower()
                browser.close()
                if not redirected:
                    return {"success": True, "error": "", "status": "已登录"}
                return {"success": False, "error": "Cookie 已过期", "status": "Cookie过期"}
        except Exception as e:
            return {"success": False, "error": str(e), "status": "连接失败"}

    def publish(self, article: Article, **kwargs) -> dict:
        """使用 Playwright 发布到知乎专栏"""
        if not self.cookie_str:
            return {"success": False, "error": "未配置 Cookie", "url": "", "id": "", "message": ""}

        save_as_draft = kwargs.get("save_as_draft", True)
        result = {"success": False, "url": "", "id": "", "error": "", "message": ""}

        title_limit = self.PLATFORM_LIMITS.get("zhihu.com", {}).get("max_title_length", 200)
        title = article.title[:title_limit]

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, args=[
                    '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                ])
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080}, locale="zh-CN",
                )
                ctx.add_cookies(self._cookies())
                page = ctx.new_page()

                try:
                    # 1. 预热 — 先访问首页建立会话
                    page.goto("https://www.zhihu.com/", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    self.logger.info("✅ 首页加载完成")

                    # 2. 打开专栏编辑器
                    page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)

                    if "signin" in page.url.lower() or "login" in page.url.lower():
                        raise PublishError("Cookie 已过期，需重新登录")
                    self.logger.info(f"✅ 编辑器已打开")

                    # 3. 填写标题
                    # 知乎专栏标题输入框：通常为输入框或 contenteditable
                    title_selectors = [
                        "input[placeholder*='标题']",
                        ".WriteIndex-titleInput input",
                        "input[placeholder*='请输入标题']",
                        "[contenteditable='true']:not(.DraftEditor-editorContainer *)",
                        ".TitleInput input",
                        "h1[contenteditable]",
                    ]
                    title_filled = False
                    for sel in title_selectors:
                        el = page.locator(sel).first
                        if el.count() > 0 and el.is_visible():
                            el.fill(title)
                            self.logger.info(f"✅ 标题已填写 (selector: {sel})")
                            title_filled = True
                            break
                    if not title_filled:
                        # 兜底：JS 直接注入
                        page.evaluate(f"""
                            (() => {{
                                const inputs = document.querySelectorAll('input[type="text"], [contenteditable="true"]');
                                for (const el of inputs) {{
                                    if (el.offsetParent !== null) {{
                                        el.focus();
                                        document.execCommand('insertText', false, {json.dumps(title)});
                                        break;
                                    }}
                                }}
                            }})()
                        """)
                        self.logger.info("✅ 标题已通过 JS 注入")
                    self.logger.info(f"✅ 标题: {title[:40]}...")

                    # 4. 填写正文
                    body = article.body or article.content or ""
                    if body:
                        # 知乎编辑器使用 Draft.js，正文区域是 contenteditable div
                        body_selectors = [
                            ".DraftEditor-editorContainer [contenteditable='true']",
                            "[contenteditable='true']",
                            ".public-DraftEditor-content",
                            "div[role='textbox']",
                        ]
                        body_filled = False
                        for sel in body_selectors:
                            el = page.locator(sel).first
                            if el.count() > 0 and el.is_visible():
                                el.evaluate(f"el => el.innerText = {json.dumps(body)}")
                                body_filled = True
                                self.logger.info(f"✅ 正文已填写 (selector: {sel})")
                                break
                        if not body_filled:
                            page.evaluate(f"""
                                (() => {{
                                    const editors = document.querySelectorAll('[contenteditable="true"]');
                                    if (editors.length > 0) {{
                                        for (const ed of editors) {{
                                            if (ed.innerText.trim() === '' || ed.innerText.length < 10) {{
                                                ed.innerText = {json.dumps(body)};
                                                break;
                                            }}
                                        }}
                                    }}
                                }})()
                            """)
                            self.logger.info("✅ 正文已通过 JS 注入")

                    # 5. 处理图片
                    image_warnings = []
                    body_text = body
                    if article.images:
                        for img_path in article.images[:5]:
                            if os.path.isfile(img_path):
                                zh_url = self._upload_image(page, img_path)
                                if zh_url:
                                    body_text = body_text.replace(img_path, zh_url)
                                    self.logger.info(f"  ✅ 图片: {zh_url[:50]}")
                                else:
                                    image_warnings.append(f"图片上传失败: {img_path}")

                    # 6. 存草稿或发布
                    if save_as_draft:
                        draft_selectors = [
                            "button:has-text('存为草稿')",
                            "button:has-text('保存草稿')",
                            "button:has-text('草稿')",
                            "[class*='draft'] button",
                        ]
                        draft_saved = False
                        for sel in draft_selectors:
                            btn = page.locator(sel).first
                            if btn.count() > 0 and btn.is_visible():
                                btn.click()
                                page.wait_for_timeout(3000)
                                self.logger.info("✅ 已存草稿")
                                result["message"] = "draft_saved"
                                draft_saved = True
                                break
                        if not draft_saved:
                            self.logger.warning("⚠️ 未找到存草稿按钮，跳过")
                            result["message"] = "no_draft_button"
                    else:
                        pub_selectors = [
                            "button:has-text('发布')",
                            "button:has-text('发布文章')",
                            "button:has-text('发表')",
                        ]
                        for sel in pub_selectors:
                            btn = page.locator(sel).first
                            if btn.count() > 0 and btn.is_visible():
                                btn.click()
                                page.wait_for_timeout(5000)
                                self.logger.info("✅ 已发布")
                                result["message"] = "published"
                                break

                    # 7. 尝试提取文章 ID
                    current_url = page.url
                    m = re.search(r'/p/(\d+)', current_url)
                    if m:
                        result["id"] = m.group(1)
                        result["url"] = f"https://zhuanlan.zhihu.com/p/{m.group(1)}"

                    result["success"] = True
                    if image_warnings:
                        result["error"] = "; ".join(image_warnings[:3])

                except PublishError:
                    raise
                except Exception as e:
                    raise PublishError(f"知乎发布失败: {str(e)}") from e
                finally:
                    page.close()
                    browser.close()

        except PublishError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)

        return result

    def _upload_image(self, page, local_path: str) -> str:
        """Playwright 上传图片到知乎图床"""
        if not os.path.isfile(local_path):
            return ""

        file_input = page.locator("input[type='file']").first
        if file_input.count() == 0:
            return ""

        try:
            file_input.set_input_files(local_path)
            page.wait_for_timeout(5000)
            html = page.content()
            # 知乎图片 URL 格式：https://pic[1-4].zhimg.com/... / https://pica.zhimg.com/...
            urls = re.findall(r'https://pic[a-z0-9]*\.zhimg\.com/[^\s"\'<>]+', html)
            if urls:
                return urls[-1]  # 最后一个通常是刚上传的
        except:
            pass
        return ""

    def upload_image(self, local_path: str) -> dict:
        """上传图片到知乎图床"""
        url = self._upload_image(None, local_path)
        if url:
            return {"success": True, "url": url, "error": ""}
        return {"success": False, "url": "", "error": "上传失败"}
