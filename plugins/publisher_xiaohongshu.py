"""
小红书 (Xiaohongshu) Publisher — Playwright 浏览器自动化（sync API）

基于实际探索结果：
- 编辑器: https://www.xiaohongshu.com/explore/editor
- 技术栈: Vue.js
- 图片+文字笔记类型，不支持独立图床上传
- 存草稿 / 发布 均支持
"""
import re, json, os, logging
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

EDITOR_URL = "https://www.xiaohongshu.com/explore/editor"
XHS_URL = "https://www.xiaohongshu.com"


def _parse_cookies(cookie_str: str) -> list:
    """解析 Cookie 字符串为 Playwright 格式"""
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        n, v = n.strip(), v.strip()
        if not n:
            continue
        cookies.append({"name": n, "value": v, "domain": ".xiaohongshu.com", "path": "/"})
    return cookies


@register
class XiaohongshuPublisher(Publisher):
    name = "xiaohongshu"
    display_name = "小红书"
    architecture = "自研 Vue.js"

    PLATFORM_LIMITS = {
        "xiaohongshu.com": {
            "max_title_length": 20,
            "min_title_length": 1,
            "supports_draft": True,
            "supports_schedule": False,
            "supports_cover": True,
            "supports_tags": True,
            "max_images": 18,
            "min_images": 1,
            "article_types": ["note"],
            "image_upload": "playwright",
        }
    }

    login_methods = [
        {"method": "phone", "label": "📞 手机验证码登录", "icon": "📞", "priority": 1,
         "fields": ["phone"],
         "description": "输入手机号，小红书发送验证码登录"},
        {"method": "qrcode", "label": "📱 扫码登录", "icon": "📱", "priority": 2,
         "fields": [],
         "description": "打开小红书登录页二维码，用手机 App 扫码"},
        {"method": "oauth", "label": "🔗 第三方账号登录", "icon": "🔗", "priority": 3,
         "fields": [],
         "description": "使用微信/QQ/微博第三方账号登录"},
        {"method": "cookie", "label": "🍪 Cookie 粘贴（备选）", "icon": "🍪", "priority": 99,
         "fields": ["cookie"],
         "description": "登录后从浏览器 F12 → Application → Cookies → xiaohongshu.com 复制"},
    ]
    config_fields = [
        {"key": "phone", "label": "手机号", "type": "text", "required": False, "default": ""},
        {"key": "cookie", "label": "Cookie（备选）", "type": "password", "required": False,
         "placeholder": "小红书全站 Cookie（从 F12 复制）"},
    ]
    supports_draft = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.logger = logging.getLogger(f"publisher.{self.name}")

    def _cookies(self):
        """返回解析后的 Cookie 列表"""
        return _parse_cookies(self.cookie_str) if self.cookie_str else []

    def test_connection(self) -> dict:
        """测试 Cookie 有效性，通过 Playwright 打开页面验证用户名存在"""
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
                page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                # 获取页面文本检测登录态
                body_text = page.inner_text("body")[:2000]

                # 检测登录态：有用户相关元素 且 无「登录/注册」按钮
                has_login_btn = bool(re.search(r'登录|注册', body_text))

                # 检测用户菜单/头像区域（登录后存在）
                user_selectors = [
                    "div[class*='user']", "div[class*='avatar']",
                    "div[class*='user-center']", "div[class*='user-info']",
                    "div[class*='user-menu']",
                ]
                has_user_menu = any(
                    page.locator(s).count() > 0 for s in user_selectors
                )

                # 尝试提取用户名/昵称
                username_hint = ""
                name_selectors = [
                    "span[class*='nickname']", "span[class*='name']",
                    "span[class*='username']", "div[class*='nickname']",
                ]
                for sel in name_selectors:
                    if username_hint:
                        break
                    els = page.locator(sel)
                    for i in range(min(els.count(), 5)):
                        t = els.nth(i).inner_text()
                        if t and len(t.strip()) < 30:
                            username_hint = t.strip()[:30]
                            break

                # 方法2: 从页面欢迎文本中提取
                if not username_hint:
                    m = re.search(r'(?:Hi|你好|欢迎)[：:\\s]*([^\\s。！，、，用户]{2,20})', body_text)
                    if m:
                        username_hint = m.group(1).strip()[:30]

                # 判定：有用户菜单 + 无登录按钮 → 已登录
                is_logged_in = has_user_menu and not has_login_btn

                browser.close()
                if is_logged_in:
                    status = f"✅ 已登录 — {username_hint}" if username_hint else "✅ 已登录"
                    return {"success": True, "error": "", "status": status}
                return {"success": False, "error": "❌ Cookie 已失效（未检测到登录态）", "status": "Cookie 过期"}
        except Exception as e:
            return {"success": False, "error": str(e), "status": "连接失败"}

    def publish(self, article: Article, **kwargs) -> dict:
        """使用 Playwright 发布到小红书"""
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
                    page.goto("https://www.xiaohongshu.com/explore", wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    self.logger.info("✅ 首页加载完成")

                    # 2. 打开编辑器
                    page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)

                    if "login" in page.url.lower() or "passport" in page.url:
                        raise PublishError("Cookie 已过期，需重新登录")
                    self.logger.info(f"✅ 编辑器已打开: {page.url}")

                    # 3. 上传图片（小红书核心内容 — 图片笔记）
                    image_warnings = []
                    images_to_upload = article.assets or []
                    if images_to_upload and len(images_to_upload) > 0:
                        valid_images = [p for p in images_to_upload[:18] if os.path.isfile(p)]
                        if valid_images:
                            file_input = page.locator("input[type='file']").first
                            if file_input.count() > 0:
                                file_input.set_input_files(valid_images)
                                # 等待图片上传完成
                                page.wait_for_timeout(5000)
                                self.logger.info(f"✅ 已上传 {len(valid_images)} 张图片")
                            else:
                                self.logger.warning("⚠️ 未找到文件上传输入框")
                                image_warnings.append("未找到文件上传控件")
                        else:
                            image_warnings.append("图片文件不存在")
                    else:
                        self.logger.warning("⚠️ 笔记未包含图片（小红书笔记通常需要至少1张图）")

                    # 4. 填写标题
                    title_input = page.locator(
                        "input[placeholder*='标题'], input[class*='title'], "
                        "input[placeholder*='填写标题']"
                    ).first
                    if title_input.count() > 0:
                        title_input.fill(article.title[:20])
                        self.logger.info(f"✅ 标题: {article.title[:20]}")
                    else:
                        self.logger.warning("⚠️ 未找到标题输入框")

                    # 5. 填写正文
                    body = article.body or article.content or ""
                    if body:
                        # 小红书编辑器正文区域 — contenteditable div 或 textarea
                        body_sel = page.locator(
                            "div[contenteditable='true'], textarea, "
                            "div[class*='text-editor'], "
                            "div[class*='note-content']"
                        ).first
                        if body_sel.count() > 0:
                            body_sel.evaluate(f"el => el.innerText = {json.dumps(body)}")
                            self.logger.info(f"✅ 正文已填写 ({len(body)} chars)")
                        else:
                            # 兜底: 通过 JS 查找
                            page.evaluate(f"""
                                (() => {{
                                    const el = document.querySelector(
                                        '[contenteditable="true"], textarea, .ql-editor'
                                    );
                                    if (el) el.innerText = {json.dumps(body)};
                                }})()
                            """)
                            self.logger.info("✅ 正文已通过JS填写")

                    # 6. 存草稿或发布（默认存草稿）
                    if save_as_draft:
                        draft_btn = page.locator(
                            "button:has-text('草稿'), button:has-text('存草稿'), "
                            "span:has-text('草稿'), span:has-text('存草稿')"
                        ).first
                        if draft_btn.count() > 0 and draft_btn.is_visible():
                            draft_btn.click()
                            page.wait_for_timeout(3000)
                            self.logger.info("✅ 已存草稿")
                            result["message"] = "draft"
                        else:
                            self.logger.warning("⚠️ 未找到存草稿按钮")
                    else:
                        pub_btn = page.locator(
                            "button:has-text('发布'), button:has-text('发表'), "
                            "span:has-text('发布'), span:has-text('发表')"
                        ).first
                        if pub_btn.count() > 0:
                            pub_btn.click()
                            page.wait_for_timeout(5000)
                            self.logger.info("✅ 已发布")
                            result["message"] = "published"
                        else:
                            self.logger.warning("⚠️ 未找到发布按钮")

                    # 尝试获取笔记 ID / URL
                    html = page.content()
                    current_url = page.url
                    note_patterns = [
                        r'/explore/([0-9a-f]{24})',
                        r'/explore/([a-zA-Z0-9_\-]{20,})',
                        r'/discovery/item/([0-9a-f]{24})',
                    ]
                    for pattern in note_patterns:
                        m = re.search(pattern, html + current_url)
                        if m:
                            result["id"] = m.group(1)
                            result["url"] = f"{XHS_URL}/explore/{m.group(1)}"
                            break

                    result["success"] = True
                    if image_warnings:
                        result["error"] = "; ".join(image_warnings[:3])

                except PublishError:
                    raise
                except Exception as e:
                    raise PublishError(f"小红书发布失败: {str(e)}") from e
                finally:
                    page.close()
                    browser.close()

        except PublishError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)

        return result

    def upload_image(self, local_path: str) -> dict:
        """小红书不支持独立图床上传，图片必须随笔记一起发布"""
        return {"success": False, "url": "", "error": "小红书不支持独立图床上传，图片需随笔记一起发布"}
