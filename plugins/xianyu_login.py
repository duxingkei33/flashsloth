"""
闲鱼 (Xianyu/goofish.com) Playwright 浏览器登录器

登录流程：
1. Playwright 打开 goofish.com
2. 点击"登录"按钮 → 跳转到淘宝 SSO (login.taobao.com)
3. 填入淘宝账号密码
4. 处理验证码/扫码 (滑块验证、二维码扫码、短信验证等)
5. 登录成功后获取 Cookie 并保存

注意：
- 淘宝登录有强反爬机制，大概率需要扫码（手机淘宝/阿里钱盾扫描二维码）
- 本模块支持截图返回前端交互，用户协助处理验证码/扫码
- 单账号不超过 3次/分钟登录（含重试）
- 预留手机端 User-Agent 模拟方案（注释说明，供后续切换）

闲鱼手机端 User-Agent (供参考):
  Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15
  (KHTML, like Gecko) Mobile/15E148 alipayClient/10.6.68
  闲鱼 App WebView 内嵌 UA
"""
import os, re, time, json, base64, random
from typing import Optional


# 登录频率控制
_LOGIN_HISTORY: dict[str, list[float]] = {}  # {account: [timestamp, ...]}
_MAX_LOGIN_PER_MINUTE = 3


def _rate_limit_check(account: str) -> tuple[bool, float]:
    """检查账号是否超过登录频率限制

    返回: (允许登录?, 还需等待秒数)
    """
    now = time.time()
    history = _LOGIN_HISTORY.get(account, [])
    # 清理1分钟前的记录
    history = [t for t in history if now - t < 60]
    _LOGIN_HISTORY[account] = history

    if len(history) >= _MAX_LOGIN_PER_MINUTE:
        wait = 60 - (now - history[0])
        return False, max(1, wait)

    return True, 0


def _record_login_attempt(account: str):
    """记录一次登录尝试"""
    if account not in _LOGIN_HISTORY:
        _LOGIN_HISTORY[account] = []
    _LOGIN_HISTORY[account].append(time.time())


def _find_chromium() -> str:
    """查找可用的 Chromium 浏览器路径"""
    candidates = [
        os.path.expanduser("~/.hermes/playwright-browsers/chromium-1228/chrome-linux64/chrome"),
        "/tmp/chrome-extracted/chrome-linux64/chrome",
        "/opt/hermes/.playwright/chromium-1228/chrome",
    ]
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    try:
        import subprocess
        r = subprocess.run(
            ["python3", "-c", "import playwright; print(playwright.__path__[0])"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            pw_path = r.stdout.strip()
            browser_path = os.path.join(
                os.path.dirname(pw_path),
                "browsers", "chromium-1228", "chrome-linux64", "chrome",
            )
            if os.path.isfile(browser_path):
                return browser_path
    except Exception:
        pass
    return ""


def _random_delay(min_ms: float = 50, max_ms: float = 300):
    """人类行为模拟：随机延时"""
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


class XianyuPlaywrightLogin:
    """闲鱼 Playwright 浏览器登录器

    处理淘宝 SSO 登录流程：
    - 扫码登录 (手机淘宝/闲鱼 App)
    - 密码 + 滑块验证码
    - 短信验证码验证

    用法:
        login = XianyuPlaywrightLogin()
        result = login.login(taobao_account="138xxxx", password="xxx")
        if result.get("needs_captcha"):
            # 前端展示截图 → 用户处理 → 调用 check_login_status()
            ...
        cookies = login.get_cookies()
    """

    # ─── 基础配置 ────────────────────────────────────
    GOOFISH_URL = "https://goofish.com"
    # 淘宝 SSO 登录页（可能变种）
    TAOBAO_LOGIN_URLS = [
        "https://login.taobao.com/member/login.jhtml",
        "https://login.taobao.com/",
    ]
    # 淘宝 SSO 跳转域名（用于检测是否处于 SSO 流程中）
    SSO_DOMAINS = [
        "login.taobao.com",
        "login.alibaba.com",
        "log.mmstat.com",
        "passport.alibaba.com",
        "login.tmall.com",
    ]

    def __init__(self, site_url: str = GOOFISH_URL):
        self.site_url = site_url.rstrip("/")
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self._captcha_screenshot = None
        self._login_started_at: Optional[float] = None
        self._account: str = ""

    def _ensure_browser(self):
        """确保浏览器已启动"""
        if self.browser and self.page:
            try:
                self.page.title()
                return
            except Exception:
                pass

        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        chrome_path = _find_chromium()

        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            # 淘宝反爬：隐藏 WebDriver 特征
            "--disable-blink-features=AutomationControlled",
            "--disable-features=ChromeWhatsNewUI",
        ]

        if chrome_path:
            self.browser = self._pw.chromium.launch(
                headless=True,
                executable_path=chrome_path,
                args=launch_args,
            )
        else:
            self.browser = self._pw.chromium.launch(
                headless=True,
                args=launch_args,
            )

        # 桌面端 User-Agent（默认）
        # 如需模拟手机端，可替换为：
        #   Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X)
        #   AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148
        #   注意：手机 UA 下 goofish.com 可能重定向到 App 下载页
        self.context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            # 注入额外 Cookie/Storage 避免被检测
            permissions=["clipboard-read", "clipboard-write"],
        )

        # 注入反检测脚本 — 隐藏 Navigator.webdriver
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en'],
            });
            // 覆盖 chrome.runtime 检测
            window.chrome = {runtime: {}};
        """)

        self.page = self.context.new_page()

    def close(self):
        """关闭浏览器"""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    def take_screenshot(self, selector: str = None) -> str:
        """截图并返回 base64"""
        self._ensure_browser()
        if selector:
            try:
                el = self.page.wait_for_selector(selector, timeout=5000)
                screenshot = el.screenshot()
            except Exception:
                screenshot = self.page.screenshot()
        else:
            screenshot = self.page.screenshot()
        return base64.b64encode(screenshot).decode()

    # ─── 登录主流程 ──────────────────────────────────

    def login(self, taobao_account: str = "", password: str = "",
              captcha_provider: str = "manual") -> dict:
        """执行 Playwright 登录闲鱼

        流程:
        1. 访问 goofish.com
        2. 点击登录按钮 → 跳转淘宝 SSO
        3. 填入淘宝账号密码
        4. 检测验证码/扫码 → 截图返回
        5. 用户处理后通过 check_login_status() 确认

        参数:
            taobao_account: 淘宝账号（手机号/邮箱）
            password: 淘宝密码
            captcha_provider: 验证方式 (manual=人工处理)

        返回:
            success: bool          — 操作是否正常执行
            logged_in: bool        — 是否最终登录成功
            needs_captcha: bool    — 是否需要验证码/扫码
            captcha_type: str      — "qr_scan" | "slider" | "sms" | "none"
            image: str             — 截图（base64），用于展示给用户
            qr_url: str            — 二维码 URL（如果检测到二维码）
            error: str
            cookies: str           — 登录成功的 cookie 字符串
            message: str           — 提示信息
        """
        self._account = taobao_account
        self._login_started_at = time.time()

        # -- 频率限制 --
        if taobao_account:
            allowed, wait = _rate_limit_check(taobao_account)
            if not allowed:
                return {
                    "success": False,
                    "logged_in": False,
                    "needs_captcha": False,
                    "error": f"登录过于频繁，请等待 {int(wait)} 秒后再试",
                }

        try:
            self._ensure_browser()
            page = self.page

            # ── 第1步：访问 goofish.com ──────────────
            page.goto(self.site_url, wait_until="networkidle", timeout=30000)
            _random_delay(200, 500)

            # ── 第2步：点击登录按钮 ──────────────────
            login_clicked = self._click_login_button()
            if not login_clicked:
                # 可能已经登录了，检查 cookie
                cookies_list = self.context.cookies() if self.context else []
                if self._has_auth_cookies(cookies_list):
                    cookie_str = self._cookies_to_str(cookies_list)
                    return {
                        "success": True, "logged_in": True,
                        "needs_captcha": False, "cookies": cookie_str,
                        "error": "",
                    }
                return {
                    "success": False, "logged_in": False,
                    "needs_captcha": False,
                    "error": "未找到登录按钮，可能页面结构已变更",
                }

            # 等待跳转到淘宝 SSO 登录页面
            _random_delay(300, 800)
            try:
                page.wait_for_url(
                    lambda url: any(d in url.lower() for d in self.SSO_DOMAINS),
                    timeout=15000,
                )
            except Exception:
                # 可能没有跳转，先检查是否已经登录
                pass

            _random_delay(200, 500)

            # ── 第3步：检测当前登录状态 ──────────────
            current_url = page.url.lower()
            cookies_list = self.context.cookies() if self.context else []

            # 检查是否直接登录成功（已跳回 goofish）
            if "goofish" in current_url and self._has_auth_cookies(cookies_list):
                cookie_str = self._cookies_to_str(cookies_list)
                _record_login_attempt(taobao_account)
                return {
                    "success": True, "logged_in": True,
                    "needs_captcha": False, "cookies": cookie_str,
                    "error": "",
                }

            # 检查是否已打开淘宝登录页
            on_login_page = any(d in current_url for d in self.SSO_DOMAINS)

            if not on_login_page:
                # 可能自动登录成功，截屏检查
                screenshot_b64 = self.take_screenshot()
                cookies_list = self.context.cookies() if self.context else []
                if self._has_auth_cookies(cookies_list):
                    cookie_str = self._cookies_to_str(cookies_list)
                    _record_login_attempt(taobao_account)
                    return {
                        "success": True, "logged_in": True,
                        "needs_captcha": False, "cookies": cookie_str,
                        "error": "",
                    }
                return {
                    "success": True, "logged_in": False,
                    "needs_captcha": True, "image": screenshot_b64,
                    "captcha_type": "unknown",
                    "message": "页面状态异常，请查看截图确认",
                    "error": "",
                }

            # ── 第4步：在淘宝登录页填入账号密码 ──────
            if taobao_account and password:
                filled = self._fill_taobao_login(taobao_account, password, page)
                if not filled.get("success"):
                    return filled

            # ── 第5步：检测验证方式 ──────────────────
            _random_delay(500, 1000)
            captcha_info = self._detect_captcha(page)

            if captcha_info.get("captcha_type") == "none":
                # 尝试直接提交（如果已填入账号密码）
                if taobao_account and password:
                    submit_result = self._submit_login(page)
                    if submit_result.get("success"):
                        cookies_list = self.context.cookies() if self.context else []
                        if self._has_auth_cookies(cookies_list):
                            cookie_str = self._cookies_to_str(cookies_list)
                            _record_login_attempt(taobao_account)
                            return {
                                "success": True, "logged_in": True,
                                "needs_captcha": False,
                                "cookies": cookie_str, "error": "",
                            }
                    return submit_result

            # 需要用户交互 — 截图返回
            screenshot_b64 = self.take_screenshot()
            return {
                "success": True,
                "logged_in": False,
                "needs_captcha": True,
                "image": screenshot_b64,
                "captcha_type": captcha_info.get("captcha_type", "unknown"),
                "qr_url": captcha_info.get("qr_url", ""),
                "message": self._get_captcha_message(captcha_info.get("captcha_type", "unknown")),
                "error": "",
            }

        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"Playwright 登录异常: {e}",
            }

    # ─── 内部方法 ─────────────────────────────────────

    def _click_login_button(self) -> bool:
        """点击闲鱼首页的登录按钮

        返回 True 表示已点击，False 表示未找到
        """
        page = self.page
        login_selectors = [
            # goofish.com 登录按钮（常见选择器）
            "a.login-link",
            "span.login-link",
            ".login-btn",
            "button:has-text('登录')",
            "a:has-text('登录')",
            "span:has-text('登录')",
            "[class*='login']",
            "[data-track*='login']",
        ]

        for sel in login_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=3000)
                if el and el.is_visible():
                    _random_delay(100, 200)
                    el.click()
                    return True
            except Exception:
                continue

        # 尝试在 iframe 中查找
        try:
            iframes = page.query_selector_all("iframe")
            for iframe_el in iframes:
                try:
                    frame = iframe_el.content_frame()
                    if frame:
                        for sel in login_selectors[:3]:
                            el = frame.wait_for_selector(sel, timeout=2000)
                            if el and el.is_visible():
                                _random_delay(100, 200)
                                el.click()
                                return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    def _fill_taobao_login(self, account: str, password: str, page) -> dict:
        """在淘宝登录页填入账号密码

        处理两种登录 Tab：
        - 密码登录（默认）
        - 扫码登录（检测到二维码则返回提示）

        返回: {"success": bool, "needs_captcha": bool, ...}
        """
        _random_delay(200, 500)

        # ── 检查是否有密码登录 Tab ──────────────────
        # 淘宝登录页有 "扫码登录" / "密码登录" 切换
        pwd_tab = None
        qr_tab = None

        try:
            # 查找密码登录 tab
            pwd_tab = page.query_selector(
                "a:has-text('密码登录'), "
                "span:has-text('密码登录'), "
                "[class*='pwd-login'], "
                "[class*='password-login']"
            )
            qr_tab = page.query_selector(
                "a:has-text('扫码登录'), "
                "img[class*='qrcode'], "
                "[class*='qr-code'], "
                "[id*='qrcode']"
            )
        except Exception:
            pass

        # 如果当前是扫码模式，尝试切换到密码登录
        if qr_tab and self._is_qr_mode(page):
            # 检测到二维码，可能不需要切 — 返回让用户扫码
            # 但如果用户提供了密码，尝试切到密码登录 tab
            if pwd_tab and pwd_tab.is_visible():
                _random_delay(100, 200)
                pwd_tab.click()
                _random_delay(300, 600)
                page.wait_for_timeout(1000)
            else:
                return {
                    "success": True,
                    "needs_captcha": True,
                    "captcha_type": "qr_scan",
                    "message": "检测到二维码，请使用手机淘宝/闲鱼 App 扫码登录",
                }

        # ── 填入账号 ────────────────────────────────
        account_selectors = [
            "input[name='fm-login-id']",
            "input[name='TPL_username']",
            "input#fm-login-id",
            "input[id*='username']",
            "input[type='text'][class*='login']",
            "input[placeholder*='账号']",
            "input[placeholder*='手机']",
            "input[placeholder*='邮箱']",
        ]

        account_filled = False
        for sel in account_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=3000)
                if el and el.is_visible():
                    _random_delay(80, 200)
                    el.click()
                    _random_delay(50, 150)
                    el.fill("")
                    _random_delay(50, 150)
                    el.type(account, delay=50)
                    account_filled = True
                    break
            except Exception:
                continue

        if not account_filled:
            return {
                "success": False, "logged_in": False,
                "error": "未找到淘宝账号输入框",
            }

        _random_delay(150, 300)

        # ── 填入密码 ────────────────────────────────
        password_selectors = [
            "input[name='fm-login-password']",
            "input[name='TPL_password']",
            "input#fm-login-password",
            "input[type='password']",
            "input[placeholder*='密码']",
        ]

        password_filled = False
        for sel in password_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=3000)
                if el and el.is_visible():
                    _random_delay(80, 200)
                    el.click()
                    _random_delay(50, 150)
                    el.fill("")
                    _random_delay(50, 150)
                    el.type(password, delay=50)
                    password_filled = True
                    break
            except Exception:
                continue

        if not password_filled:
            return {
                "success": False, "logged_in": False,
                "error": "未找到淘宝密码输入框",
            }

        _random_delay(100, 300)

        # ── 尝试点击登录按钮 ────────────────────────
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('登录')",
            "input[type='submit']",
            "[class*='submit']",
            "[class*='login-btn']",
        ]

        for sel in submit_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=3000)
                if el and el.is_visible():
                    _random_delay(100, 200)
                    el.click()
                    break
            except Exception:
                continue

        _random_delay(500, 1000)

        return {"success": True}

    def _is_qr_mode(self, page) -> bool:
        """检测当前是否是扫码登录模式"""
        try:
            # 检测二维码图片
            qr_img = page.query_selector(
                "img[class*='qrcode'], "
                "img[id*='qr'], "
                "canvas[id*='qrcode']"
            )
            if qr_img:
                return True
            # 检测页面上是否有 "请使用手机淘宝扫码" 等文字
            content = page.content()
            qr_keywords = [
                "扫码", "二维码", "qrcode", "QR",
                "请使用手机", "扫一扫",
            ]
            for kw in qr_keywords:
                if kw in content:
                    return True
        except Exception:
            pass
        return False

    def _detect_captcha(self, page) -> dict:
        """检测淘宝登录页的验证方式

        返回:
            captcha_type: "qr_scan" | "slider" | "sms" | "none"
            qr_url: str (如果有二维码可提取 URL)
        """
        page_content = page.content()
        result = {"captcha_type": "none", "qr_url": ""}

        # 1. 检测二维码扫码
        if self._is_qr_mode(page):
            qr_url = self._extract_qr_url(page)
            result["captcha_type"] = "qr_scan"
            result["qr_url"] = qr_url
            return result

        # 2. 检测滑块验证码 (Alibaba 滑块)
        slider_keywords = [
            "nc_scale",
            "nc-container",
            "nc_1__scale_text",
            "slider",
            "滑动验证",
            "请按住滑块",
            "drag",
        ]
        for kw in slider_keywords:
            if kw in page_content:
                result["captcha_type"] = "slider"
                return result

        # 3. 检测短信验证码
        sms_keywords = [
            "短信验证",
            "验证码已发送",
            "请输入验证码",
            "sms-code",
            "sendCode",
        ]
        for kw in sms_keywords:
            if kw in page_content:
                result["captcha_type"] = "sms"
                return result

        # 4. 检测是否需要点击验证图片
        click_keywords = [
            "请依次点击",
            "图片验证",
            "captcha-img",
            "verify-img",
            "geetest",
        ]
        for kw in click_keywords:
            if kw in page_content:
                result["captcha_type"] = "click_image"
                return result

        return result

    def _extract_qr_url(self, page) -> str:
        """尝试提取二维码中的 URL"""
        try:
            # 尝试从 img 的 src 获取
            qr_img = page.query_selector(
                "img[class*='qrcode'], img[id*='qr']"
            )
            if qr_img:
                src = qr_img.get_attribute("src")
                if src and src.startswith("http"):
                    return src

            # 尝试从 canvas 获取
            qr_canvas = page.query_selector(
                "canvas[id*='qrcode'], canvas[class*='qrcode']"
            )
            if qr_canvas:
                # 某些实现可能有 data-url 属性
                url_attr = qr_canvas.get_attribute("data-url")
                if url_attr:
                    return url_attr
        except Exception:
            pass
        return ""

    def _submit_login(self, page) -> dict:
        """尝试提交登录表单

        返回: {"success": bool, "needs_captcha": bool, ...}
        """
        _random_delay(200, 400)

        # 查找并点击提交按钮
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('登录')",
            "input[type='submit']",
        ]
        for sel in submit_selectors:
            try:
                el = page.wait_for_selector(sel, timeout=3000)
                if el and el.is_visible():
                    _random_delay(100, 200)
                    el.click()
                    break
            except Exception:
                continue

        # 等待跳转（3秒内完成登录跳转）
        _random_delay(500, 1000)
        try:
            page.wait_for_url(
                lambda url: "goofish.com" in url.lower(),
                timeout=5000,
            )
        except Exception:
            pass

        # 检查登录状态
        cookies_list = self.context.cookies() if self.context else []
        if self._has_auth_cookies(cookies_list):
            cookie_str = self._cookies_to_str(cookies_list)
            _record_login_attempt(self._account)
            return {
                "success": True, "logged_in": True,
                "needs_captcha": False, "cookies": cookie_str,
                "error": "",
            }

        # 检查是否弹出了验证码
        captcha_info = self._detect_captcha(page)
        if captcha_info.get("captcha_type") != "none":
            screenshot_b64 = self.take_screenshot()
            return {
                "success": True, "logged_in": False,
                "needs_captcha": True, "image": screenshot_b64,
                "captcha_type": captcha_info["captcha_type"],
                "message": self._get_captcha_message(captcha_info["captcha_type"]),
                "error": "",
            }

        return {
            "success": False, "logged_in": False,
            "needs_captcha": False,
            "error": "登录提交失败，请检查账号密码是否正确",
        }

    def _get_captcha_message(self, captcha_type: str) -> str:
        """根据验证码类型返回中文提示"""
        messages = {
            "qr_scan": "请使用手机淘宝/闲鱼 App 扫描二维码登录（浏览器截图在下方）",
            "slider": "请完成滑块验证码（拖动滑块到指定位置）",
            "sms": "短信验证码已发送到您的手机，请输入验证码",
            "click_image": "请按照提示点击图片中的指定文字/物品",
            "unknown": "页面需要额外验证，请查看截图并操作",
        }
        return messages.get(captcha_type, "请查看截图并完成验证")

    def _has_auth_cookies(self, cookies_list: list) -> bool:
        """检查 cookie 中是否包含淘宝/闲鱼认证标记"""
        auth_names = {
            "_tb_token_",
            "cookie2",
            "t",
            "sid",
            "alimamapwg",
            "munb",
            "ucn",
            "lgc",
            "x5sec",
            "sg",
            "snsInfo",
        }
        cookie_names = set(c.get("name", "") for c in cookies_list)
        hits = auth_names & cookie_names
        return len(hits) >= 3  # 至少命中3个关键 cookie

    def _cookies_to_str(self, cookies_list: list) -> str:
        """将 cookie 列表拼接为字符串"""
        return "; ".join(
            f"{c['name']}={c['value']}"
            for c in cookies_list
            if c.get("name") and c.get("value")
        )

    # ─── 公开方法 ─────────────────────────────────────

    def check_login_status(self) -> dict:
        """检测当前登录状态（在用户处理验证码/扫码后调用）

        返回同 login() 格式
        """
        try:
            self._ensure_browser()
            cookies_list = self.context.cookies() if self.context else []

            if self._has_auth_cookies(cookies_list):
                cookie_str = self._cookies_to_str(cookies_list)
                _record_login_attempt(self._account)
                return {
                    "success": True, "logged_in": True,
                    "needs_captcha": False, "cookies": cookie_str,
                    "error": "",
                }

            # 检查当前页面 URL
            page = self.page
            current_url = page.url.lower()

            # 如果已经跳回 goofish，重试检查 cookie
            if "goofish.com" in current_url:
                _random_delay(200, 500)
                cookies_list = self.context.cookies() if self.context else []
                if self._has_auth_cookies(cookies_list):
                    cookie_str = self._cookies_to_str(cookies_list)
                    _record_login_attempt(self._account)
                    return {
                        "success": True, "logged_in": True,
                        "needs_captcha": False, "cookies": cookie_str,
                        "error": "",
                    }

            # 还在登录页 — 截图返回
            screenshot_b64 = self.take_screenshot()
            captcha_info = self._detect_captcha(page)
            return {
                "success": True,
                "logged_in": False,
                "needs_captcha": True,
                "image": screenshot_b64,
                "captcha_type": captcha_info.get("captcha_type", "unknown"),
                "message": "登录尚未完成，请继续操作",
                "error": "",
            }

        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"检查登录状态异常: {e}",
            }

    def get_cookies(self) -> str:
        """获取当前浏览器的 cookie 字符串"""
        try:
            cookies_list = self.context.cookies() if self.context else []
            return self._cookies_to_str(cookies_list)
        except Exception:
            return ""

    def is_logged_in(self) -> bool:
        """检查当前浏览器是否已登录"""
        try:
            cookies_list = self.context.cookies() if self.context else []
            return self._has_auth_cookies(cookies_list)
        except Exception:
            return False
