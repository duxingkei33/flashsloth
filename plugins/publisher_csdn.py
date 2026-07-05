"""
CSDN Publisher — Playwright 浏览器自动化（严格 Playwright，无 requests/curl）

基于实际探索结果：
- 编辑器: https://editor.csdn.net/md/?not_checkout=1
- 标题: input[placeholder*='标题']
- 正文: .editor__inner.markdown-highlighting (Markdown 模式)
- 存草稿: button:has-text('保存草稿')
- 发布: button:has-text('发布文章')
"""
import re, json, os, urllib.parse
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.async_api import async_playwright

EDITOR_URL = "https://editor.csdn.net/md/?not_checkout=1"
BLOG_URL = "https://blog.csdn.net"

def _parse_cookies(cookie_str: str) -> list:
    """解析 CSDN Cookie 为 Playwright 格式"""
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
        {"method": "cookie", "label": "Cookie 粘贴", "icon": "🍪", "priority": 1,
         "fields": ["cookie"],
         "description": "登录后从浏览器 F12 → Application → Cookies → csdn.net 复制"},
    ]
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "CSDN 全站 Cookie（从 F12 复制）"},
        {"key": "article_type", "label": "默认文章类型", "type": "select", "required": False,
         "default": "original",
         "options": [
             {"value": "original", "label": "原创"},
             {"value": "reprint", "label": "转载"},
             {"value": "translated", "label": "翻译"},
         ]},
        {"key": "category", "label": "默认分类", "type": "text", "required": False,
         "placeholder": "分类名称（可选）"},
        {"key": "tags", "label": "默认标签", "type": "text", "required": False,
         "placeholder": "逗号分隔的标签（可选）"},
    ]
    supports_draft = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.article_type = config.get("article_type", "original")
        self._cookies = None

    @property
    def cookies(self) -> list:
        if self._cookies is None and self.cookie_str:
            self._cookies = _parse_cookies(self.cookie_str)
        return self._cookies or []

    async def _ensure_browser(self, pw):
        """创建浏览器上下文并注入 Cookie"""
        browser = await pw.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
        ])
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        if self.cookies:
            await ctx.add_cookies(self.cookies)
        return browser, ctx

    async def verify_login(self) -> bool:
        """验证 Cookie 是否有效"""
        if not self.cookies:
            return False
        async with async_playwright() as pw:
            browser, ctx = await self._ensure_browser(pw)
            page = await ctx.new_page()
            try:
                await page.goto("https://www.csdn.net/", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                # 检测是否登录
                login_links = await page.query_selector_all("a:has-text('登录')")
                user_els = await page.query_selector_all("[class*='avatar'], [class*='user-info']")
                ok = len(login_links) == 0 or len(user_els) > 0
                return ok
            except:
                return False
            finally:
                await page.close()
                await browser.close()

    async def publish(self, article: Article, dry_run: bool = False) -> dict:
        """使用 Playwright 发布到 CSDN"""
        if not self.cookies:
            raise PublishError("未配置 Cookie")

        result = {"url": "", "status": "unknown", "platform_id": ""}

        async with async_playwright() as pw:
            browser, ctx = await self._ensure_browser(pw)
            page = await ctx.new_page()

            try:
                # 1. 预热 — 先访问首页建立会话
                await page.goto("https://www.csdn.net/", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)
                self.logger.info("✅ 首页加载完成")

                # 2. 打开编辑器
                await page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)  # 等 JS 渲染

                # 检查是否跳转登录
                if "passport" in page.url or "login" in page.url.lower():
                    raise PublishError("Cookie 已过期，需重新登录")

                self.logger.info(f"✅ 编辑器已打开: {page.url}")

                # 3. 填写标题
                title_input = await page.query_selector("input[placeholder*='标题']")
                if title_input:
                    await title_input.fill(article.title[:100])
                    self.logger.info(f"✅ 标题: {article.title[:40]}...")
                else:
                    raise PublishError("找不到标题输入框")

                # 4. 填写正文（Markdown 模式）
                body = article.body or article.content or ""
                if body:
                    # 使用 JS 直接设置 editor 内容
                    # CSDN 编辑器实际是 contenteditable div
                    editor_div = await page.query_selector(".editor__inner.markdown-highlighting, .editor")
                    if editor_div:
                        await editor_div.evaluate(f"el => el.innerText = {json.dumps(body)}")
                        self.logger.info(f"✅ 正文已填写 ({len(body)} chars)")
                    else:
                        # 备用：通过 CodeMirror API
                        await page.evaluate(f"""
                            (() => {{
                                const el = document.querySelector('.editor');
                                if (el) el.innerText = {json.dumps(body)};
                            }})()
                        """)
                        self.logger.info("✅ 正文已通过 JS 备用方式填写")

                # 5. 处理图片（纯 Playwright 方式）
                image_warnings = []
                if article.images:
                    for img_path in article.images[:10]:
                        try:
                            # 通过编辑器上传 — 用拖拽或文件输入
                            csdn_url = await self._upload_image_playwright(page, img_path)
                            if csdn_url:
                                # 替换正文中的本地 URL
                                body = body.replace(img_path, csdn_url)
                                body = body.replace(os.path.basename(img_path), csdn_url)
                                self.logger.info(f"  ✅ 图片上传: {csdn_url[:50]}")
                            else:
                                image_warnings.append(f"图片上传失败: {img_path}")
                        except Exception as e:
                            image_warnings.append(f"图片异常: {str(e)[:60]}")

                    # 重新填写带 CSDN 图床 URL 的正文
                    if body:
                        editor_div = await page.query_selector(".editor")
                        if editor_div:
                            await editor_div.evaluate(f"el => el.innerText = {json.dumps(body)}")

                if dry_run:
                    result["status"] = "draft_saved"
                    result["url"] = page.url
                    return result

                # 6. 存草稿
                draft_btn = await page.query_selector("button:has-text('保存草稿')")
                if draft_btn:
                    await draft_btn.click()
                    await page.wait_for_timeout(3000)
                    self.logger.info("✅ 已存草稿")
                    result["status"] = "draft_saved"
                else:
                    self.logger.warning("⚠️ 未找到存草稿按钮")
                    result["status"] = "unknown"

                # 获取文章 URL
                result["url"] = page.url

                # 尝试从页面或URL中提取文章ID
                page_html = await page.content()
                for pattern in [r'article/details/(\d+)', r'articleId=(\d+)']:
                    m = re.search(pattern, page_html + page.url)
                    if m:
                        result["platform_id"] = m.group(1)
                        result["url"] = f"{BLOG_URL}/duxingkei/article/details/{m.group(1)}"
                        break

            except PublishError:
                raise
            except Exception as e:
                raise PublishError(f"CSDN 发布失败: {str(e)}") from e
            finally:
                await page.close()
                await browser.close()

        return result

    async def _upload_image_playwright(self, page, local_path: str) -> str:
        """纯 Playwright 方式上传图片到 CSDN

        通过编辑器内置的图片上传功能（拖拽或文件选择器）
        """
        if not os.path.isfile(local_path):
            self.logger.warning(f"  ⚠️ 图片文件不存在: {local_path}")
            return ""

        # 1. 找文件上传 input
        file_input = await page.query_selector("input[type='file']")
        if not file_input:
            self.logger.warning("  ⚠️ 未找到 file input")
            return ""

        # 2. 设置文件
        try:
            await file_input.set_input_files(local_path)
            await page.wait_for_timeout(5000)  # 等上传
        except Exception as e:
            self.logger.warning(f"  ⚠️ 文件选择失败: {e}")
            return ""

        # 3. 等待上传完成，从页面提取 CSDN 图片 URL
        await page.wait_for_timeout(3000)
        html = await page.content()
        img_urls = re.findall(r'https://img-blog\.csdnimg\.cn/[^\s\"\'<>]+', html)
        if img_urls:
            return img_urls[0]

        # 4. 备用：通过拖拽上传
        try:
            # 找到编辑器区域拖放
            editor = await page.query_selector(".editor")
            if editor:
                # 创建 DataTransfer 事件
                await page.evaluate(f"""
                    (async () => {{
                        const blob = new Blob(['fake'], {{ type: 'image/png' }});
                        const file = new File([blob], '{os.path.basename(local_path)}', {{ type: 'image/png' }});
                        const dt = new DataTransfer();
                        dt.items.add(file);
                        const el = document.querySelector('.editor');
                        if (el) {{
                            const event = new DragEvent('drop', {{ dataTransfer: dt }});
                            el.dispatchEvent(event);
                        }}
                    }})()
                """)
                await page.wait_for_timeout(5000)
                html = await page.content()
                img_urls = re.findall(r'https://img-blog\.csdnimg\.cn/[^\s\"\'<>]+', html)
                if img_urls:
                    return img_urls[0]
        except:
            pass

        self.logger.warning("  ⚠️ 图片上传后未检测到 CSDN 图床 URL")
        return ""

    async def check_signin(self) -> dict:
        """CSDN 签到"""
        # CSDN 签到主要通过每日任务完成，暂不做签到验证
        return {"success": False, "message": "CSDN 签到功能待实现"}
