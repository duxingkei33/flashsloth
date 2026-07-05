"""
OHWHub Publisher — 基于 Playwright 的立创开源硬件平台发布器
"""
import json, re
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.async_api import async_playwright

BASE = "https://oshwhub.com"

def _parse_cookie_string(cookie_str: str) -> list:
    """将分号分隔的 cookie string 转为 Playwright cookie list"""
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": ".oshwhub.com",
            "path": "/",
        })
    return cookies


@register
class OSHWHubPublisher(Publisher):
    name = "oshwhub"
    display_name = "立创开源硬件平台"
    login_methods = [
        {
            "method": "password",
            "label": "密码+验证码登录",
            "icon": "🔑",
            "priority": 1,
            "fields": ["username", "password"],
            "description": "使用嘉立创账号密码登录（可能触发滑块验证码）",
        },
        {
            "method": "cookie",
            "label": "Cookie 粘贴",
            "icon": "🍪",
            "priority": 2,
            "fields": ["cookie"],
            "description": "从浏览器 F12 → Application → Cookies → oshwhub.com 复制 Cookie",
        },
    ]
    config_fields = [
        {
            "key": "username",
            "label": "用户名/手机号",
            "type": "text",
            "required": False,
            "placeholder": "嘉立创账号（手机号或邮箱）",
        },
        {
            "key": "password",
            "label": "密码",
            "type": "password",
            "required": False,
        },
        {
            "key": "cookie",
            "label": "Cookie（完整 Cookie 字符串）",
            "type": "password",
            "required": False,
            "placeholder": "从浏览器 F12 → Application → Cookies → oshwhub.com 复制",
        },
    ]
    supports_draft = True
    supports_cover = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self._cookies = None

    @property
    def cookies(self) -> list:
        if self._cookies is None and self.cookie_str:
            self._cookies = _parse_cookie_string(self.cookie_str)
        return self._cookies or []

    async def verify_login(self) -> bool:
        """验证 Cookie 是否有效"""
        if not self.cookies:
            return False
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=[
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
            ])
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            await ctx.add_cookies(self.cookies)
            page = await ctx.new_page()
            try:
                await page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                # 检测登录态：看是否有用户名/头像
                avatar = await page.query_selector("[class*='user-avatar']")
                login_links = await page.query_selector_all("a:has-text('登录')")
                ok = avatar is not None or len(login_links) == 0
                return ok
            finally:
                await page.close()
                await browser.close()

    async def publish(self, article: Article, dry_run: bool = False) -> dict:
        """发布文章到 OSHWHub

        使用 Playwright 模拟浏览器全流程操作。
        """
        if not self.cookies and not (self.username and self.password):
            raise PublishError("未配置登录凭证，请先添加 Cookie 或账号密码")

        result = {"url": "", "status": "unknown", "platform_id": ""}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=[
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
            ])
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )

            # 注入 Cookie
            if self.cookies:
                await ctx.add_cookies(self.cookies)

            page = await ctx.new_page()

            try:
                # 导航到创建页
                await page.goto(f"{BASE}/project/create", wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)  # 等 JS 渲染

                # 检查是否被重定向到登录页
                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise PublishError("Cookie 已过期，需重新登录")

                # 1. 填写工程名称
                name_input = await page.wait_for_selector("#name", timeout=5000)
                await name_input.fill(article.title)
                self.logger.info(f"✅ 填写工程名称: {article.title[:30]}...")

                # 2. 填写工程简介
                intro = article.summary or article.content[:100]
                intro_input = await page.wait_for_selector("#introduction", timeout=5000)
                await intro_input.fill(intro[:100])

                # 3. 填写总成本（可选）
                if article.tags and any("成本" in t for t in article.tags):
                    try:
                        cost_input = await page.query_selector("input[placeholder='请填写总成本']")
                        if cost_input:
                            await cost_input.fill("100")
                    except:
                        pass

                # 4. TinyMCE 正文
                # 等待 TinyMCE 加载完成
                await page.wait_for_selector(".tox-tinymce", timeout=10000)

                # 通过 TinyMCE API 写入内容
                tinymce_content = article.content

                # 尝试通过 tinymce activeEditor 注入
                await page.evaluate(f"""
                    (() => {{
                        const editor = tinymce?.activeEditor;
                        if (editor) {{
                            editor.setContent({json.dumps(tinymce_content)});
                        }}
                    }})()
                """)

                # 备用：通过 iframe body 写入
                tinymce_iframe = await page.query_selector(".tox-tinymce iframe")
                if tinymce_iframe:
                    frame = await tinymce_iframe.content_frame()
                    if frame:
                        body = await frame.query_selector("body")
                        if body:
                            # 如果 tinymce API 没生效，直接操作 iframe body
                            await body.evaluate(f"el => el.innerHTML = {json.dumps(tinymce_content)}")

                # 5. 处理图片
                if article.images:
                    for img_url in article.images[:5]:  # 最多5张
                        try:
                            # 展开 TinyMCE 图片上传
                            upload_btn = await page.query_selector("button:has-text('上传图片')")
                            if upload_btn and await upload_btn.is_visible():
                                await upload_btn.click()
                                await page.wait_for_timeout(2000)
                                # 这里需要处理文件上传对话框
                        except:
                            pass

                if dry_run:
                    result["status"] = "draft_saved"
                    result["url"] = page.url
                    return result

                # 6. 点击创建按钮
                create_btn = await page.query_selector("button:has-text('创建')")
                if not create_btn:
                    create_btn = await page.query_selector("button:has-text('创 建')")
                if create_btn:
                    await create_btn.click()
                    await page.wait_for_timeout(5000)
                    result["url"] = page.url
                    result["status"] = "published"

                    # 从 URL 提取平台 ID
                    m = re.search(r'/project/([a-zA-Z0-9]+)', page.url)
                    if m:
                        result["platform_id"] = m.group(1)
                else:
                    result["status"] = "draft_saved"
                    result["url"] = page.url

            except PublishError:
                raise
            except Exception as e:
                raise PublishError(f"OSHWHub 发布失败: {str(e)}") from e
            finally:
                await page.close()
                await browser.close()

        return result

    async def check_signin(self) -> dict:
        """执行签到"""
        if not self.cookies:
            return {"success": False, "message": "未配置 Cookie"}

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=[
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
            ])
            ctx = await browser.new_context()
            await ctx.add_cookies(self.cookies)
            page = await ctx.new_page()

            try:
                await page.goto(f"{BASE}/user/signin", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(5000)

                # 尝试所有可能的签到按钮选择器
                for sel in [
                    "button:has-text('签到')",
                    "button:has-text('打卡')",
                    "button:has-text('领积分')",
                    "[class*='sign-btn']",
                ]:
                    btn = await page.query_selector(sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await page.wait_for_timeout(3000)
                        return {"success": True, "message": "签到成功"}

                return {"success": False, "message": "未找到签到按钮，请确认签到入口"}
            finally:
                await page.close()
                await browser.close()
