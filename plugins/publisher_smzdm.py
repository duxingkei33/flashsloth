"""
什么值得买 (smzdm) Publisher — Playwright 浏览器自动化（sync API）

基于实际探索结果：
- 平台: https://www.smzdm.com/
- 编辑器: https://www.smzdm.com/publish
- 登录: 密码 / 手机验证码 / 微信/QQ/微博 OAuth / Cookie 粘贴
- 技术栈: Tencent Cloud WAF (JS Challenge + 拖拽验证码)
- 内容类型: 好价爆料、优惠信息，非纯文本博客

注意：smzdm 是消费导购平台，发布内容为"爆料"（deal submission），
包含商品标题、价格、渠道、推荐理由等结构化字段，非纯 Markdown 编辑器。
"""
import re
import json
import os
import logging
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.smzdm.com/"
EDITOR_URL = "https://www.smzdm.com/publish"
DOMAIN = ".smzdm.com"


def _parse_cookies(cookie_str: str) -> list:
    """解析 Cookie 字符串为 Playwright 格式"""
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        cookies.append({"name": n.strip(), "value": v.strip(), "domain": DOMAIN, "path": "/"})
    return cookies


def _human_delay(page, min_ms: int = 500, max_ms: int = 2000):
    """模拟人类行为的随机延迟"""
    import random
    delay = random.randint(min_ms, max_ms)
    page.wait_for_timeout(delay)


def _handle_waf(page) -> bool:
    """
    检测并尝试处理 Tencent Cloud WAF 挑战。

    返回 True 表示 WAF 已通过，False 表示仍在 WAF 页面。
    """
    current_url = page.url.lower()
    page_title = page.title().lower()

    # 检测 WAF / JS 挑战页
    is_waf = False
    for indicator in ["waf", "tencent", "captcha", "js挑战", "人机验证", "安全检查"]:
        if indicator in current_url or indicator in page_title or indicator in page.content().lower():
            is_waf = True
            break

    if not is_waf:
        return True  # 没有 WAF，直接通过

    logging.getLogger("publisher.smzdm").warning("⚠️ 检测到 WAF/JS 挑战，等待处理...")
    page.wait_for_timeout(5000)
    _human_delay(page, 2000, 4000)

    # 再次检测是否已通过
    for indicator in ["waf", "tencent", "captcha", "js挑战", "人机验证"]:
        if indicator in page.url.lower() or indicator in page.title().lower():
            return False  # 仍然被 WAF 拦截

    return True


@register
class SmzdmPublisher(Publisher):
    name = "smzdm"
    display_name = "什么值得买"
    architecture = "消费导购平台（自研CMS）"

    PLATFORM_LIMITS = {
        "smzdm.com": {
            "max_title_length": 60,
            "min_title_length": 2,
            "supports_draft": True,
            "supports_schedule": False,
            "supports_cover": True,
            "supports_tags": True,
            "article_types": ["deal", "article"],
            "image_upload": "playwright",
        }
    }

    login_methods = [
        {"method": "password", "label": "🔑 账号密码登录", "icon": "🔑", "priority": 1,
         "fields": ["username", "password"],
         "description": "输入什么值得买用户名和密码，Playwright 浏览器自动登录（可能触发 Tencent WAF 验证码）"},
        {"method": "phone", "label": "📞 手机验证码登录", "icon": "📞", "priority": 2,
         "fields": ["phone"],
         "description": "输入手机号，Playwright 自动发送验证码并等待用户输入"},
        {"method": "oauth", "label": "🔗 第三方账号登录", "icon": "🔗", "priority": 3,
         "fields": ["oauth_provider"],
         "description": "微信/QQ/微博快捷登录（需要浏览器交互）"},
        {"method": "cookie", "label": "🍪 Cookie 粘贴（备选）", "icon": "🍪", "priority": 99,
         "fields": ["cookie"],
         "description": "登录后从浏览器 F12 → Application → Cookies → smzdm.com 复制完整 Cookie"},
    ]

    config_fields = [
        {"key": "username", "label": "用户名/手机号/邮箱", "type": "text", "required": False, "default": ""},
        {"key": "password", "label": "密码", "type": "password", "required": False, "default": ""},
        {"key": "phone", "label": "手机号（短信验证码登录）", "type": "text", "required": False, "default": ""},
        {"key": "cookie", "label": "Cookie（备选，优先级最高）", "type": "password", "required": False,
         "placeholder": "smzdm.com 完整 Cookie（从 F12 复制）"},
        {"key": "default_category", "label": "默认分类", "type": "select", "required": False,
         "default": "all",
         "options": [
             {"value": "all", "label": "全部好价"},
             {"value": "shuma", "label": "数码"},
             {"value": "meishi", "label": "食品"},
             {"value": "muying", "label": "母婴"},
             {"value": "fushi", "label": "服饰"},
             {"value": "riyong", "label": "日用"},
             {"value": "hudong", "label": "互动"},
         ]},
        {"key": "publish_type", "label": "发布类型", "type": "select", "required": False,
         "default": "deal",
         "options": [
             {"value": "deal", "label": "好价爆料"},
             {"value": "article", "label": "原创文章"},
         ]},
    ]
    supports_draft = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.phone = config.get("phone", "")
        self.default_category = config.get("default_category", "all")
        self.publish_type = config.get("publish_type", "deal")
        self.logger = logging.getLogger(f"publisher.{self.name}")

    def _cookies(self):
        return _parse_cookies(self.cookie_str) if self.cookie_str else []

    def _launch_browser(self):
        """创建 Playwright 浏览器实例（带 WAF 抗检测参数）"""
        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            geolocation={"latitude": 39.9042, "longitude": 116.4074},
            permissions=["geolocation"],
        )
        # 添加 Cookie（如有）
        if self.cookie_str:
            try:
                ctx.add_cookies(self._cookies())
            except Exception as e:
                self.logger.warning(f"⚠️ Cookie 格式异常: {e}")

        page = ctx.new_page()
        # 注入反检测脚本
        page.add_init_script("""
            // 覆盖 webdriver 检测
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // 覆盖 chrome 属性检测
            window.chrome = { runtime: {} };
            // 覆盖权限检测
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) => (
                params.name === 'notifications' ?
                Promise.resolve({state: 'denied'}) :
                originalQuery(params)
            );
            // 覆盖 plugins 和 mimeTypes 长度
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
        """)
        return pw, browser, ctx, page

    def test_connection(self) -> dict:
        """测试 Cookie 有效性，提取用户名"""
        if not self.cookie_str:
            return {"success": False, "error": "未配置 Cookie", "status": "无凭证"}

        pw = browser = ctx = page = None
        try:
            pw, browser, ctx, page = self._launch_browser()
            page.goto("https://www.smzdm.com/", wait_until="domcontentloaded", timeout=30000)

            # 处理可能的 WAF 挑战
            _handle_waf(page)

            # 等待页面完全渲染
            page.wait_for_timeout(5000)
            _human_delay(page)

            body_text = page.inner_text("body")[:3000]
            page_url = page.url

            # 检查页面是否被 WAF 拦截
            if "waf" in page_url.lower() or "tencent" in page_url.lower():
                return {"success": False, "error": "❌ 被 Tencent WAF 拦截，请尝试更换 IP 或重试", "status": "WAF拦截"}

            # 检查登录态指标
            has_logout = bool(re.search(r'退出|注销|登出', body_text))
            has_avatar = bool(re.search(r'avatar|用户头像|我的头像', body_text, re.IGNORECASE))
            has_username_link = bool(re.search(r'class="[^"]*uname[^"]*"', body_text)) or \
                               bool(re.search(r'user-name|nickname|用户昵称', body_text, re.IGNORECASE))
            has_my_smzdm = bool(re.search(r'我的值得买|个人中心|我的收藏|我的订单', body_text))

            # 尝试提取用户名
            username_hint = ""
            # 方法1: 页面中的 welcome/欢迎 文本
            m = re.search(r'(欢迎|Hi|你好)[：:：\\s]+([^\\s。！，,]{2,20})', body_text)
            if m:
                username_hint = m.group(2).strip()

            # 方法2: 配置中的用户名出现在页面文本中
            if not username_hint and self.username:
                if self.username in body_text:
                    username_hint = self.username

            # 方法3: uname 相关元素
            if not username_hint:
                uname_els = page.locator('[class*="uname"], [class*="nickname"], .J_user_name')
                if uname_els.count() > 0:
                    username_hint = uname_els.first.inner_text().strip()

            # 判定规则
            strong_exit = has_logout
            indicators = sum([has_logout, has_avatar, has_username_link, has_my_smzdm])
            is_logged_in = strong_exit and (indicators >= 2 or bool(username_hint))

            if is_logged_in:
                status = f"✅ 已登录 — {username_hint}" if username_hint else "✅ 已登录"
                return {"success": True, "error": "", "status": status}
            return {"success": False, "error": "❌ Cookie 已失效（未检测到登录态）", "status": "Cookie过期"}
        except Exception as e:
            return {"success": False, "error": str(e), "status": "连接失败"}
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass

    def publish(self, article: Article, **kwargs) -> dict:
        """使用 Playwright 发布到什么值得买

        smzdm 的发布流程分为两种：
        - 好价爆料 (deal): 标题、商品价格、购买渠道、推荐理由、图片
        - 原创文章 (article): 标题、正文 Markdown

        参数:
            article: Article 对象
            kwargs:
                save_as_draft: 是否存草稿 (默认 True)
                price: 商品价格（好价爆料）
                channel: 购买渠道（好价爆料）
                category: 分类
        """
        if not self.cookie_str and not (self.username and self.password):
            return {"success": False, "error": "未配置 Cookie 或账号密码", "url": "", "id": ""}

        save_as_draft = kwargs.get("save_as_draft", True)
        price = kwargs.get("price", "")
        channel = kwargs.get("channel", "")
        category = kwargs.get("category", self.default_category)
        result = {"success": False, "url": "", "id": "", "error": "", "message": ""}

        pw = browser = ctx = page = None
        try:
            pw, browser, ctx, page = self._launch_browser()

            # 1. 预热 — 先访问首页建立会话
            self.logger.info("🌐 访问 smzdm 首页...")
            page.goto("https://www.smzdm.com/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 处理 WAF
            if not _handle_waf(page):
                self.logger.warning("⚠️ WAF 拦截首页，等待重试...")
                page.wait_for_timeout(8000)
                if not _handle_waf(page):
                    raise PublishError("Tencent WAF 拦截，当前 IP 被限制，请稍后重试或更换网络")
            self.logger.info("✅ 首页加载完成")

            # 2. 打开发布页面
            self.logger.info(f"📝 打开发布页: {EDITOR_URL}")
            page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            _human_delay(page)

            # 检查是否被跳转回登录页
            if "passport" in page.url or "login" in page.url.lower():
                raise PublishError("Cookie 已过期或登录态丢失，需重新登录")

            # 处理可能的 WAF
            if not _handle_waf(page):
                raise PublishError("发布页被 Tencent WAF 拦截，请稍后重试")

            self.logger.info(f"✅ 发布页已打开: {page.url}")

            # 3. 根据发布类型处理
            if self.publish_type == "deal":
                self._publish_deal(page, article, price, channel, category, save_as_draft, result)
            else:
                self._publish_article(page, article, category, save_as_draft, result)

            # 尝试获取发布后的 URL / ID
            if not result["url"]:
                html = page.content()
                current_url = page.url
                for pattern in [r'/deal/(\d+)', r'/article/(\d+)', r'publish/(\d+)',
                                r'smzdm\.com/(\d+)', r'smzdm\.com/p/(\d+)']:
                    m = re.search(pattern, html + current_url)
                    if m:
                        result["id"] = m.group(1)
                        if self.publish_type == "deal":
                            result["url"] = f"https://www.smzdm.com/deal/{m.group(1)}/"
                        else:
                            result["url"] = f"https://www.smzdm.com/article/{m.group(1)}/"
                        break

            result["success"] = True
            self.logger.info(f"✅ 发布完成: {result['url'] or 'URL 未知'}")

        except PublishError as e:
            result["error"] = str(e)
            self.logger.error(f"❌ {e}")
        except Exception as e:
            err_msg = f"smzdm 发布失败: {str(e)}"
            result["error"] = err_msg
            self.logger.error(f"❌ {err_msg}")
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass

        return result

    def _publish_deal(self, page, article: Article, price: str, channel: str,
                      category: str, save_as_draft: bool, result: dict):
        """好价爆料发布流程"""
        self.logger.info("📢 好价爆料模式")

        # 尝试切换到"好价" Tab（如果有 tab 选择）
        try:
            deal_tab = page.locator("a:has-text('好价爆料'), button:has-text('好价'), "
                                    "li:has-text('好价'), span:has-text('好价')").first
            if deal_tab.count() > 0 and deal_tab.is_visible():
                deal_tab.click()
                _human_delay(page)
                self.logger.info("✅ 已选择好价爆料 Tab")
        except Exception:
            pass

        # 3.1 填写商品标题
        title = article.title[:60]
        title_selectors = [
            "input[placeholder*='商品名称'], input[placeholder*='标题'], input[placeholder*='产品']",
            "input[name*='title'], input[name*='name'], input[name*='goods']",
            "#title, .title-input, .goods-name",
        ]
        title_filled = False
        for selector in title_selectors:
            title_input = page.locator(selector).first
            if title_input.count() > 0 and title_input.is_visible():
                title_input.click()
                _human_delay(page)
                title_input.fill(title)
                title_filled = True
                self.logger.info(f"✅ 标题: {title[:30]}...")
                break

        if not title_filled:
            self.logger.warning("⚠️ 未找到标题输入框，尝试通用填充")
            all_inputs = page.locator("input[type='text'], input:not([type])")
            for i in range(min(all_inputs.count(), 5)):
                try:
                    placeholder = all_inputs.nth(i).get_attribute("placeholder") or ""
                    if any(kw in placeholder for kw in ["商品", "标题", "名称", "产品", "输入"]):
                        all_inputs.nth(i).fill(title)
                        title_filled = True
                        self.logger.info(f"✅ 标题已填写 (第{i+1}个输入框)")
                        break
                except Exception:
                    continue

        _human_delay(page)

        # 3.2 填写商品价格
        if price:
            price_selectors = [
                "input[placeholder*='价格'], input[placeholder*='金额'], input[placeholder*='现价']",
                "input[name*='price'], input[name*='money']",
                "#price, .price-input",
            ]
            for selector in price_selectors:
                price_input = page.locator(selector).first
                if price_input.count() > 0 and price_input.is_visible():
                    price_input.click()
                    _human_delay(page)
                    price_input.fill(price)
                    self.logger.info(f"✅ 价格: {price}")
                    break

        # 3.3 填写购买渠道
        if channel:
            channel_selectors = [
                "input[placeholder*='渠道'], input[placeholder*='平台'], input[placeholder*='电商']",
                "input[placeholder*='购买'], input[name*='channel'], input[name*='source']",
                "#channel, .channel-input",
            ]
            for selector in channel_selectors:
                ch_input = page.locator(selector).first
                if ch_input.count() > 0 and ch_input.is_visible():
                    ch_input.click()
                    _human_delay(page)
                    ch_input.fill(channel)
                    self.logger.info(f"✅ 购买渠道: {channel}")
                    break

        # 3.4 填写推荐理由（正文）
        body_text = (article.body or article.summary or "")
        if body_text:
            body_selectors = [
                "textarea[placeholder*='推荐理由'], textarea[placeholder*='描述'], textarea[placeholder*='说明']",
                "textarea[name*='desc'], textarea[name*='reason'], textarea[name*='content']",
                "#description, .desc-editor, .reason-editor",
                "div[contenteditable='true']",
                ".ql-editor, .editor-content",
            ]
            body_filled = False
            for selector in body_selectors:
                body_el = page.locator(selector).first
                if body_el.count() > 0 and body_el.is_visible():
                    tag = body_el.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "textarea":
                        body_el.click()
                        _human_delay(page)
                        body_el.fill(body_text[:1000])
                    elif tag in ("div", "span", "p") and body_el.get_attribute("contenteditable"):
                        body_el.click()
                        _human_delay(page)
                        body_el.evaluate(f"el => el.innerText = {json.dumps(body_text[:1000])}")
                    else:
                        body_el.click()
                        _human_delay(page)
                        body_el.fill(body_text[:1000])
                    body_filled = True
                    self.logger.info(f"✅ 推荐理由已填写 ({len(body_text[:1000])} chars)")
                    break

            if not body_filled:
                self.logger.warning("⚠️ 未找到正文/推荐理由输入框")

        _human_delay(page)

        # 3.5 上传封面图片
        if article.cover:
            try:
                file_input = page.locator("input[type='file']").first
                if file_input.count() > 0:
                    # 如果是 URL，下载到临时文件
                    if article.cover.startswith(("http://", "https://")):
                        import tempfile
                        import urllib.request
                        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                        try:
                            urllib.request.urlretrieve(article.cover, tmp.name)
                            file_input.set_input_files(tmp.name)
                            self.logger.info(f"✅ 封面图片已上传")
                        finally:
                            try:
                                os.unlink(tmp.name)
                            except Exception:
                                pass
                    elif os.path.isfile(article.cover):
                        file_input.set_input_files(article.cover)
                        self.logger.info(f"✅ 封面图片已上传")
            except Exception as e:
                self.logger.warning(f"⚠️ 图片上传失败: {e}")

        _human_delay(page)

        # 3.6 选择分类
        if category and category != "all":
            try:
                category_selectors = [
                    f"select[name*='category']",
                    f".category-select, #category",
                ]
                for selector in category_selectors:
                    cat_el = page.locator(selector).first
                    if cat_el.count() > 0:
                        cat_el.select_option(category)
                        self.logger.info(f"✅ 分类: {category}")
                        break
            except Exception as e:
                self.logger.warning(f"⚠️ 分类选择失败: {e}")

        # 3.7 存草稿或发布
        if save_as_draft:
            self._click_save_draft(page)
            result["message"] = "draft"
        else:
            self._click_publish(page)
            result["message"] = "published"

    def _publish_article(self, page, article: Article, category: str,
                         save_as_draft: bool, result: dict):
        """原创文章发布流程"""
        self.logger.info("📝 原创文章模式")

        # 切换至原创 Tab
        try:
            article_tab = page.locator("a:has-text('原创文章'), button:has-text('原创'), "
                                        "li:has-text('原创'), span:has-text('原创')").first
            if article_tab.count() > 0 and article_tab.is_visible():
                article_tab.click()
                _human_delay(page)
                self.logger.info("✅ 已选择原创文章 Tab")
        except Exception:
            pass

        # 填写标题
        title = article.title[:60]
        title_selectors = [
            "input[placeholder*='标题'], input[placeholder*='文章标题']",
            "input[name*='title'], #article-title",
        ]
        title_filled = False
        for selector in title_selectors:
            title_input = page.locator(selector).first
            if title_input.count() > 0 and title_input.is_visible():
                title_input.click()
                _human_delay(page)
                title_input.fill(title)
                title_filled = True
                self.logger.info(f"✅ 标题: {title[:30]}...")
                break

        _human_delay(page)

        # 填写正文
        body_text = article.body or article.content or ""
        if body_text:
            body_selectors = [
                "textarea[placeholder*='内容'], textarea[name*='content'], textarea[name*='body']",
                "div[contenteditable='true']",
                ".ql-editor, .editor-content",
                "#content, .article-editor",
            ]
            for selector in body_selectors:
                body_el = page.locator(selector).first
                if body_el.count() > 0 and body_el.is_visible():
                    tag = body_el.evaluate("el => el.tagName.toLowerCase()")
                    if tag == "textarea":
                        body_el.click()
                        _human_delay(page)
                        body_el.fill(body_text)
                    elif tag in ("div", "span") and body_el.get_attribute("contenteditable"):
                        body_el.click()
                        _human_delay(page)
                        body_el.evaluate(f"el => el.innerText = {json.dumps(body_text)}")
                    else:
                        body_el.click()
                        _human_delay(page)
                        body_el.fill(body_text)
                    self.logger.info(f"✅ 正文已填写 ({len(body_text)} chars)")
                    break

        _human_delay(page)

        # 存草稿或发布
        if save_as_draft:
            self._click_save_draft(page)
            result["message"] = "draft"
        else:
            self._click_publish(page)
            result["message"] = "published"

    def _click_save_draft(self, page):
        """点击存草稿按钮"""
        try:
            draft_selectors = [
                "button:has-text('存草稿'), button:has-text('保存草稿')",
                "button:has-text('草稿'), a:has-text('存草稿')",
                "#save-draft, .save-draft",
            ]
            for selector in draft_selectors:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(3000)
                    _human_delay(page)
                    self.logger.info("✅ 已存草稿")
                    return

            # 如果没找到存草稿按钮，尝试查找"预览"后再找草稿
            preview_btn = page.locator("button:has-text('预览'), a:has-text('预览')").first
            if preview_btn.count() > 0 and preview_btn.is_visible():
                preview_btn.click()
                page.wait_for_timeout(2000)
                # 预览页面可能也有存草稿
                for selector in draft_selectors:
                    btn = page.locator(selector).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click()
                        page.wait_for_timeout(3000)
                        self.logger.info("✅ 已存草稿")
                        return

            self.logger.warning("⚠️ 未找到存草稿按钮")
        except Exception as e:
            self.logger.warning(f"⚠️ 存草稿异常: {e}")

    def _click_publish(self, page):
        """点击发布按钮"""
        try:
            publish_selectors = [
                "button:has-text('发布'), button:has-text('提交'), button:has-text('发表')",
                "button:has-text('立即发布'), a:has-text('发布')",
                "#publish-btn, .publish-btn, .submit-btn",
                "input[type='submit']",
            ]
            for selector in publish_selectors:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(5000)
                    _human_delay(page)
                    self.logger.info("✅ 已发布")
                    return

            self.logger.warning("⚠️ 未找到发布按钮")
        except Exception as e:
            self.logger.warning(f"⚠️ 发布点击异常: {e}")

    def _upload_image(self, page, local_path: str) -> str:
        """上传图片到 smzdm 图床"""
        if not os.path.isfile(local_path):
            return ""

        try:
            # 查找文件上传按钮
            file_input = page.locator("input[type='file']").first
            if file_input.count() == 0:
                # 尝试点击上传按钮触发表单
                upload_trigger = page.locator(
                    "button:has-text('上传图片'), a:has-text('上传图片'), "
                    ".upload-btn, [class*='upload']"
                ).first
                if upload_trigger.count() > 0:
                    upload_trigger.click()
                    page.wait_for_timeout(2000)

                file_input = page.locator("input[type='file']").first
                if file_input.count() == 0:
                    return ""

            file_input.set_input_files(local_path)
            page.wait_for_timeout(5000)
            _human_delay(page, 1000, 3000)

            # 尝试获取上传后的图片 URL
            html = page.content()
            urls = re.findall(r'https?://[^\\s"\'<>]+\\.(?:jpg|jpeg|png|gif|webp)(?:\\?[^\\s"\'<>]*)?', html)
            # 过滤 smzdm 图床的 URL
            smzdm_urls = [u for u in urls if any(d in u for d in ["smzdm.com", "zhiimg.com", "qpic.cn"])]
            if smzdm_urls:
                return smzdm_urls[0]
            if urls:
                return urls[0]
        except Exception as e:
            self.logger.warning(f"⚠️ 图片上传失败: {e}")
        return ""

    def upload_image(self, local_path: str) -> dict:
        """上传图片到 smzdm 图床（独立接口）"""
        pw = browser = ctx = page = None
        try:
            pw, browser, ctx, page = self._launch_browser()
            # 先访问首页加载 Cookie
            page.goto("https://www.smzdm.com/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            url = self._upload_image(page, local_path)
            if url:
                return {"success": True, "url": url, "error": ""}
            return {"success": False, "url": "", "error": "上传失败"}
        except Exception as e:
            return {"success": False, "url": "", "error": str(e)}
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if pw:
                try:
                    pw.stop()
                except Exception:
                    pass

    def validate_config(self) -> list[str]:
        """验证配置完整性"""
        missing = []
        if not self.cookie_str:
            if not self.username:
                missing.append("username")
            if not self.password and not self.phone:
                missing.append("password 或 phone（二选一）")
        return missing
