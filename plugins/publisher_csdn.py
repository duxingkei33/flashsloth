"""
CSDN Publisher — Playwright 浏览器自动化（sync API）

基于实际探索结果：
- 编辑器: https://editor.csdn.net/md/?not_checkout=1
- 标题: input[placeholder*='标题']
- 正文: .editor__inner.markdown-highlighting (Markdown 模式)
- 存草稿: button:has-text('保存草稿')
- 发布: button:has-text('发布文章')
"""
import re, json, os, logging
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

EDITOR_URL = "https://editor.csdn.net/md/?not_checkout=1"
BLOG_URL = "https://blog.csdn.net"


def _parse_cookies(cookie_str: str) -> list:
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        cookies.append({"name": n.strip(), "value": v.strip(), "domain": ".csdn.net", "path": "/"})
    return cookies


@register
class CSDNPublisher(Publisher):
    name = "csdn"
    display_name = "CSDN"

    PLATFORM_LIMITS = {
        "csdn.net": {
            "max_title_length": 100,
            "min_title_length": 5,
            "supports_draft": True,
            "supports_schedule": True,
            "supports_cover": True,
            "supports_tags": True,
            "article_types": ["original", "reprint", "translated"],
            "image_upload": "playwright",
        }
    }

    login_methods = [
        {"method": "password", "label": "账号密码登录", "icon": "🔑", "priority": 1,
         "fields": ["username", "password"],
         "description": "输入 CSDN 用户名和密码，Playwright 浏览器自动登录"},
        {"method": "cookie", "label": "Cookie 粘贴（备选）", "icon": "🍪", "priority": 99,
         "fields": ["cookie"],
         "description": "登录后从浏览器 F12 → Application → Cookies → csdn.net 复制"},
    ]
    config_fields = [
        {"key": "username", "label": "用户名/邮箱", "type": "text", "required": False, "default": ""},
        {"key": "password", "label": "密码", "type": "password", "required": False, "default": ""},
        {"key": "cookie", "label": "Cookie（备选）", "type": "password", "required": False,
         "placeholder": "CSDN 全站 Cookie（从 F12 复制）"},
        {"key": "article_type", "label": "默认文章类型", "type": "select", "required": False,
         "default": "original",
         "options": [
             {"value": "original", "label": "原创"},
             {"value": "reprint", "label": "转载"},
             {"value": "translated", "label": "翻译"},
         ]},
    ]
    supports_draft = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.article_type = config.get("article_type", "original")
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
                page.goto("https://www.csdn.net/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                login_links = page.locator("a:has-text('登录')")
                ok = login_links.count() == 0
                browser.close()
                if ok:
                    return {"success": True, "error": "", "status": "已登录"}
                return {"success": False, "error": "Cookie 已过期", "status": "Cookie过期"}
        except Exception as e:
            return {"success": False, "error": str(e), "status": "连接失败"}

    def publish(self, article: Article, **kwargs) -> dict:
        """使用 Playwright 发布到 CSDN"""
        if not self.cookie_str:
            return {"success": False, "error": "未配置 Cookie", "url": "", "id": ""}

        save_as_draft = kwargs.get("save_as_draft", True)
        result = {"success": False, "url": "", "id": "", "error": "", "message": ""}

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
                    page.goto("https://www.csdn.net/", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    self.logger.info("✅ 首页加载完成")

                    # 2. 打开编辑器
                    page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)

                    if "passport" in page.url or "login" in page.url.lower():
                        raise PublishError("Cookie 已过期，需重新登录")

                    self.logger.info(f"✅ 编辑器已打开")

                    # 3. 填写标题
                    title_input = page.locator("input[placeholder*='标题']").first
                    if title_input.count() > 0:
                        title_input.fill(article.title[:100])
                        self.logger.info(f"✅ 标题: {article.title[:40]}...")
                    else:
                        raise PublishError("找不到标题输入框")

                    # 4. 填写正文
                    body = article.body or article.content or ""
                    if body:
                        editor_div = page.locator(".editor__inner.markdown-highlighting, .editor").first
                        if editor_div.count() > 0:
                            editor_div.evaluate(f"el => el.innerText = {json.dumps(body)}")
                            self.logger.info(f"✅ 正文已填写 ({len(body)} chars)")
                        else:
                            page.evaluate(f"""
                                (() => {{
                                    const el = document.querySelector('.editor');
                                    if (el) el.innerText = {json.dumps(body)};
                                }})()
                            """)
                            self.logger.info("✅ 正文已通过JS填写")

                    # 5. 处理图片
                    image_warnings = []
                    body_text = body
                    if article.images:
                        for img_path in article.images[:10]:
                            if os.path.isfile(img_path):
                                csdn_url = self._upload_image(page, img_path)
                                if csdn_url:
                                    body_text = body_text.replace(img_path, csdn_url)
                                    self.logger.info(f"  ✅ 图片: {csdn_url[:50]}")
                                else:
                                    image_warnings.append(f"图片上传失败: {img_path}")
                        if body_text != body:
                            editor_div = page.locator(".editor").first
                            if editor_div.count() > 0:
                                editor_div.evaluate(f"el => el.innerText = {json.dumps(body_text)}")

                    # 6. 存草稿或发布
                    if save_as_draft:
                        draft_btn = page.locator("button:has-text('保存草稿')").first
                        if draft_btn.count() > 0 and draft_btn.is_visible():
                            draft_btn.click()
                            page.wait_for_timeout(3000)
                            self.logger.info("✅ 已存草稿")
                            result["message"] = "draft"
                        else:
                            self.logger.warning("⚠️ 未找到存草稿按钮")
                    else:
                        pub_btn = page.locator("button:has-text('发布文章')").first
                        if pub_btn.count() > 0:
                            pub_btn.click()
                            page.wait_for_timeout(5000)
                            self.logger.info("✅ 已发布")
                            result["message"] = "published"

                    # 尝试获取文章 ID
                    html = page.content()
                    for pattern in [r'article/details/(\d+)', r'articleId=(\d+)']:
                        m = re.search(pattern, html + page.url)
                        if m:
                            result["id"] = m.group(1)
                            result["url"] = f"{BLOG_URL}/duxingkei/article/details/{m.group(1)}"
                            break

                    result["success"] = True
                    if image_warnings:
                        result["error"] = "; ".join(image_warnings[:3])

                except PublishError:
                    raise
                except Exception as e:
                    raise PublishError(f"CSDN 发布失败: {str(e)}") from e
                finally:
                    page.close()
                    browser.close()

        except PublishError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)

        return result

    def _upload_image(self, page, local_path: str) -> str:
        """纯 Playwright 上传图片"""
        if not os.path.isfile(local_path):
            return ""

        file_input = page.locator("input[type='file']").first
        if file_input.count() == 0:
            return ""

        try:
            file_input.set_input_files(local_path)
            page.wait_for_timeout(5000)
            html = page.content()
            urls = re.findall(r'https://img-blog\.csdnimg\.cn/[^\s"\'<>]+', html)
            if urls:
                return urls[0]
        except:
            pass
        return ""

    def upload_image(self, local_path: str) -> dict:
        """上传图片到 CSDN 图床"""
        url = self._upload_image(None, local_path)
        if url:
            return {"success": True, "url": url, "error": ""}
        return {"success": False, "url": "", "error": "上传失败"}
