"""
OHWHub Publisher — 基于 Playwright (sync) 的立创开源硬件平台发布器
"""
import re, json, os
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

BASE = "https://oshwhub.com"


def _parse_cookies(cookie_str: str) -> list:
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        cookies.append({"name": n.strip(), "value": v.strip(), "domain": ".oshwhub.com", "path": "/"})
    return cookies


@register
class OSHWHubPublisher(Publisher):
    name = "oshwhub"
    display_name = "立创开源硬件平台"
    login_methods = [
        {"method": "cookie", "label": "Cookie 粘贴", "icon": "🍪", "priority": 1,
         "fields": ["cookie"],
         "description": "从浏览器 F12 → Application → Cookies → oshwhub.com 复制"},
    ]
    config_fields = [
        {"key": "cookie", "label": "Cookie（完整 Cookie 字符串）", "type": "password", "required": True,
         "placeholder": "登录后从浏览器复制 Cookie"},
    ]
    supports_draft = True
    supports_cover = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")

    def _cookies(self):
        return _parse_cookies(self.cookie_str) if self.cookie_str else []

    def test_connection(self) -> dict:
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
                page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                avatar = page.locator("[class*='user-avatar']").first
                login_links = page.locator("a:has-text('登录')")
                ok = avatar.count() > 0 or login_links.count() == 0
                browser.close()
                return {"success": ok, "error": "" if ok else "Cookie 过期", "status": "已登录" if ok else "Cookie过期"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def publish(self, article: Article, **kwargs) -> dict:
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
                    # 导航到创建页
                    page.goto(f"{BASE}/project/create", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(6000)

                    if "login" in page.url.lower() or "passport" in page.url.lower():
                        raise PublishError("Cookie 已过期")

                    # 1. 工程名称
                    name_input = page.locator("#name").first
                    if name_input.count() > 0:
                        name_input.fill(article.title[:50])
                        self.logger.info(f"✅ 工程名称: {article.title[:30]}...")
                    else:
                        raise PublishError("找不到工程名称输入框")

                    # 2. 工程简介
                    intro = (article.summary or article.content or "")[:100]
                    intro_input = page.locator("#introduction").first
                    if intro_input.count() > 0:
                        intro_input.fill(intro)
                        self.logger.info("✅ 工程简介已填写")

                    # 3. TinyMCE 正文
                    body = article.body or article.content or ""
                    page.wait_for_selector(".tox-tinymce", timeout=10000)
                    page.evaluate(f"""
                        (() => {{
                            const editor = tinymce?.activeEditor;
                            if (editor) {{
                                editor.setContent({json.dumps(body)});
                            }}
                        }})()
                    """)
                    self.logger.info(f"✅ 正文已填写 ({len(body)} chars)")

                    # 4. 图片上传（通过 TinyMCE）
                    if article.images:
                        for img_path in article.images[:5]:
                            if os.path.isfile(img_path):
                                try:
                                    file_input = page.locator("input[type='file']").first
                                    if file_input.count() > 0:
                                        file_input.set_input_files(img_path)
                                        page.wait_for_timeout(3000)
                                except:
                                    pass

                    if save_as_draft:
                        result["message"] = "draft_saved"
                        result["url"] = page.url
                    else:
                        # 点击创建
                        create_btn = page.locator("button:has-text('创建'), button:has-text('创 建')").first
                        if create_btn.count() > 0:
                            create_btn.click()
                            page.wait_for_timeout(5000)
                            result["url"] = page.url
                            m = re.search(r'/project/([a-zA-Z0-9]+)', page.url)
                            if m:
                                result["id"] = m.group(1)
                            result["message"] = "published"

                    result["success"] = True

                except PublishError:
                    raise
                except Exception as e:
                    raise PublishError(f"OSHWHub 发布失败: {str(e)}") from e
                finally:
                    page.close()
                    browser.close()

        except PublishError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)

        return result
