"""FlashSloth — 通用 Playwright 登录（CSDN、wechat、bilibili、juejin、zhihu 等）

支持标准用户名/密码 + 验证码浏览器登录流程。
"""
import base64
import json
import threading
import time
import traceback
from datetime import datetime

_LOGIN_INSTANCES: dict[str, "GenericPlaywrightLogin"] = {}
_LOGIN_LOCK = threading.Lock()


def get_generic_login(session_id: str = "default") -> "GenericPlaywrightLogin":
    """获取/创建通用登录实例（线程安全：跨线程自动重建）"""
    import threading
    current_thread = threading.current_thread().ident
    with _LOGIN_LOCK:
        existing = _LOGIN_INSTANCES.get(session_id)
        if existing and getattr(existing, '_thread_id', None) == current_thread:
            return existing
        # 线程不同或不存在 → 重建
        if existing:
            try:
                existing.close()
            except Exception:
                pass
        inst = GenericPlaywrightLogin()
        inst._thread_id = current_thread
        _LOGIN_INSTANCES[session_id] = inst
        return inst


def close_generic_login(session_id: str = "default"):
    """关闭并清理通用登录实例"""
    with _LOGIN_LOCK:
        inst = _LOGIN_INSTANCES.pop(session_id, None)
    if inst:
        inst.close()


# 各平台登录页配置
LOGIN_PAGE_MAP = {
    "csdn": {
        "login_url": "https://passport.csdn.net/login",
        "username_selector": "input[type='text'], input[name*='username'], input[name*='login']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit'], .login-button, .btn-login",
        "logged_in_indicator": ["我的博客", "创作中心", "我的粉丝"],
        "auth_cookie_keywords": ["session", "token", "passport", "auth", "login"],
    },
    "bilibili": {
        "login_url": "https://www.bilibili.com/",
        "username_selector": "input[type='text']",
        "password_selector": "input[type='password']",
        "submit_selector": ".btn-login, .login-btn, button[type='submit']",
        "logged_in_indicator": ["我的消息", "投稿管理", "创作中心"],
        "auth_cookie_keywords": ["session", "bili_jct", "buvid3", "DedeUserID"],
    },
    "juejin": {
        "login_url": "https://juejin.cn/",
        "username_selector": "input[name*='login'], input[type='text']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit'], .login-btn",
        "logged_in_indicator": ["我的", "编辑资料", "创作者中心"],
        "auth_cookie_keywords": ["session", "token", "auth", "uid", "juejin"],
    },
    "zhihu": {
        "login_url": "https://www.zhihu.com/signin",
        "username_selector": "input[type='text'], input[name='username']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit'], .SignFlow-submitButton",
        "logged_in_indicator": ["我的主页", "发视频", "创作中心"],
        "auth_cookie_keywords": ["session", "token", "z_c0", "d_c0", "login", "auth"],
    },
    "wechat": {
        "login_url": "https://mp.weixin.qq.com/",
        "username_selector": "input[type='text'], input[name*='account'], input[name*='user']",
        "password_selector": "input[type='password']",
        "submit_selector": "button[type='submit'], .login-btn, .btn_login",
        "logged_in_indicator": ["首页", "新建群发", "管理", "功能"],
        "auth_cookie_keywords": ["token", "session", "uin", "key", "wxtoken"],
    },
    "wordpress": {
        "login_url": "",
        "username_selector": "input#user_login, input[name='log']",
        "password_selector": "input#user_pass, input[name='pwd']",
        "submit_selector": "input#wp-submit, button[type='submit']",
        "logged_in_indicator": ["仪表盘", "写文章", "Dashboard", "New Post", "wp-admin"],
        "auth_cookie_keywords": ["wordpress_", "wp_", "auth", "login"],
    },
}


class GenericPlaywrightLogin:
    """通用 Playwright 登录器"""

    def __init__(self):
        self._lock = threading.Lock()
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self.platform_config = {}
        self.is_running = False

    def _ensure_browser(self):
        """确保浏览器已启动（线程安全：每请求独立实例）"""
        # 已在当前线程创建 → 复用
        if self.browser and self.page and self._pw:
            try:
                self.browser.is_connected()
                return
            except Exception:
                pass
        
        # 关闭旧实例（如果有）
        self._cleanup_playwright()
        
        # 创建新实例（当前线程）
        from playwright.sync_api import sync_playwright
        try:
            pw = sync_playwright()
            self._pw = pw.__enter__()
            self.browser = self._pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                      '--disable-blink-features=AutomationControlled',
                      '--ignore-certificate-errors'],
            )
            self.context = self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            self.page = self.context.new_page()
        except Exception:
            self._cleanup_playwright()
            raise

    def _cleanup_playwright(self):
        """安全清理 Playwright 资源"""
        for attr in ['page', 'context', 'browser', '_pw']:
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    if attr == '_pw':
                        obj.__exit__(None, None, None)
                    elif attr == 'browser':
                        if obj.is_connected():
                            obj.close()
                    elif attr in ('context', 'page'):
                        obj.close()
                except Exception:
                    pass
                setattr(self, attr, None)

    def login(self, platform: str, username: str = "", password: str = "",
              site_url: str = "") -> dict:
        """启动浏览器登录流程（线程安全：每请求独立 Playwright 实例）"""
        self.platform_config = LOGIN_PAGE_MAP.get(platform, {})
        if not self.platform_config and not site_url:
            return {"success": False, "error": f"平台 {platform} 无默认登录页，请提供 site_url"}

        login_url = self.platform_config.get("login_url", site_url)
        if site_url and not login_url:
            login_url = site_url

        if not login_url:
            return {"success": False, "error": "无法确定登录地址"}

        # 每请求创建独立的 Playwright 实例，避免跨线程问题
        from playwright.sync_api import sync_playwright
        _pw = None
        _browser = None
        _context = None
        _page = None
        try:
            _pw = sync_playwright().__enter__()
            _browser = _pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                      '--disable-blink-features=AutomationControlled',
                      '--ignore-certificate-errors'],
            )
            _context = _browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            _page = _context.new_page()

            # 更新 self 供内部方法引用（take_screenshot / _check_logged_in / submit_captcha）
            self.browser = _browser
            self.context = _context
            self.page = _page
            self._pw = _pw
            page = self.page  # 局部变量简化引用

            # 导航到登录页
            page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 尝试填写用户名和密码
            if username and password:
                user_sel = self.platform_config.get("username_selector", "input[type='text']")
                pass_sel = self.platform_config.get("password_selector", "input[type='password']")

                # 填空用户名
                try:
                    user_input = page.wait_for_selector(user_sel, timeout=5000)
                    if user_input:
                        user_input.click()
                        page.fill(user_sel, username)
                except Exception:
                    pass

                # 填空密码
                try:
                    pass_input = page.wait_for_selector(pass_sel, timeout=5000)
                    if pass_input:
                        pass_input.click()
                        page.fill(pass_sel, password)
                except Exception:
                    pass

                # 尝试点击提交按钮
                sub_sel = self.platform_config.get("submit_selector", "button[type='submit']")
                try:
                    submit_btn = page.wait_for_selector(sub_sel, timeout=3000)
                    if submit_btn:
                        submit_btn.click()
                        page.wait_for_timeout(3000)
                except Exception:
                    pass

            # 等待页面稳定后检查是否已登录
            page.wait_for_timeout(2000)
            screenshot_b64 = self.take_screenshot()
            logged_in = self._check_logged_in()

            if logged_in:
                cookies = self._get_cookie_string()
                return {
                    "success": True,
                    "logged_in": True,
                    "cookies": cookies,
                    "image": screenshot_b64,
                    "message": "✅ 登录成功",
                }

            # 检查是否需要验证码
            needs_captcha = self._detect_captcha()

            result = {
                "success": True,
                "logged_in": False,
                "needs_captcha": needs_captcha,
                "image": screenshot_b64,
                "message": "🔒 需要验证码" if needs_captcha else "⏳ 请查看截图并手动操作",
            }
            return result

        except Exception as e:
            tb = traceback.format_exc()
            return {
                "success": False,
                "error": f"登录启动异常: {str(e)[:100]}",
                "traceback": tb,
                "logged_in": False,
            }

    def phone_login(self, platform: str, phone: str = "", site_url: str = "") -> dict:
        """手机验证码登录流程：打开登录页 → 切换到手机/SMS Tab → 输手机号 → 发验证码 → 截图"""
        self.platform_config = LOGIN_PAGE_MAP.get(platform, {})
        login_url = self.platform_config.get("login_url", site_url)
        if site_url and not login_url:
            login_url = site_url
        if not login_url:
            return {"success": False, "error": "无法确定登录地址"}

        # 每个请求创建独立的 Playwright 实例，避免多线程问题
        from playwright.sync_api import sync_playwright
        _pw = None
        _browser = None
        _context = None
        _page = None
        try:
            _pw = sync_playwright().__enter__()
            _browser = _pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                      '--disable-blink-features=AutomationControlled',
                      '--ignore-certificate-errors'],
            )
            _context = _browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            _page = _context.new_page()

            _page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            _page.wait_for_timeout(3000)

            # 尝试切换到手机/SMS Tab
            tab_selectors = [
                'div[class*="tab"]:has-text("手机")',
                'div[class*="tab"]:has-text("短信")',
                'a:has-text("手机")',
                'a:has-text("短信")',
                'span:has-text("手机")',
                'span:has-text("短信")',
                'button:has-text("手机")',
                'button:has-text("短信")',
                '[class*="phone"]',
            ]
            for sel in tab_selectors:
                try:
                    tab_btn = _page.wait_for_selector(sel, timeout=2000)
                    if tab_btn and tab_btn.is_visible():
                        tab_btn.click()
                        _page.wait_for_timeout(1000)
                        break
                except Exception:
                    pass

            # 填入手机号
            if phone:
                phone_sel = 'input[type="tel"], input[name*="phone"], input[id*="phone"], '
                phone_sel += 'input[placeholder*="手机"], input[placeholder*="phone"]'
                try:
                    phone_input = _page.wait_for_selector(phone_sel, timeout=5000)
                    if phone_input:
                        phone_input.click()
                        _page.fill(phone_sel, phone)
                        _page.wait_for_timeout(500)
                except Exception:
                    pass

            # 点击"发送验证码"按钮
            try:
                code_btn_selectors = [
                    'button:has-text("发送")',
                    'button:has-text("获取")',
                    'button:has-text("验证码")',
                    '[class*="send"]',
                    '[class*="captcha"]',
                ]
                for cb_sel in code_btn_selectors:
                    try:
                        send_btn = _page.wait_for_selector(cb_sel, timeout=2000)
                        if send_btn and send_btn.is_visible():
                            send_btn.click()
                            _page.wait_for_timeout(2000)
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            _page.wait_for_timeout(2000)
            screenshot_b64 = base64.b64encode(_page.screenshot(type="png", full_page=False)).decode()

            # 检测是否已有验证码输入框（表示已发送成功）
            has_code_input = False
            try:
                code_input = _page.query_selector(
                    'input[placeholder*="验证码"], input[name*="captcha"], input[id*="captcha"], '
                    'input[placeholder*="code"], input[name*="code"]'
                )
                if code_input:
                    has_code_input = True
            except Exception:
                pass

            result = {
                "success": True,
                "logged_in": False,
                "needs_captcha": True,
                "image": screenshot_b64,
                "message": "📱 验证码已发送到手机，请输入验证码" if has_code_input
                           else "📞 请输入手机号并手动发送验证码",
                "phone_input_ready": True,
            }
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"手机登录启动异常: {str(e)[:100]}",
                "logged_in": False,
            }
        finally:
            # 清理本地的 Playwright 实例（避免跨线程问题）
            try:
                if _page:
                    _page.close()
                if _context:
                    _context.close()
                if _browser:
                    _browser.close()
                if _pw:
                    _pw.__exit__(None, None, None)
            except Exception:
                pass

    def submit_captcha_and_login(self, platform: str = "") -> dict:
        """已验证码已处理，尝试提交并检查登录状态"""
        try:
            if not self.page:
                return {"success": False, "error": "浏览器未启动", "logged_in": False}

            page = self.page
            base_poll = self.platform_config if self.platform_config else LOGIN_PAGE_MAP.get(platform, {})

            # 尝试点击提交按钮再等一会
            sub_sel = base_poll.get("submit_selector", "button[type='submit']")
            try:
                submit_btn = page.wait_for_selector(sub_sel, timeout=3000)
                if submit_btn:
                    submit_btn.click()
            except Exception:
                pass

            page.wait_for_timeout(5000)
            screenshot_b64 = self.take_screenshot()
            logged_in = self._check_logged_in()

            if logged_in:
                cookies = self._get_cookie_string()
                return {
                    "success": True,
                    "logged_in": True,
                    "cookies": cookies,
                    "image": screenshot_b64,
                    "message": "✅ 登录成功！Cookie 已自动获取",
                }

            return {
                "success": True,
                "logged_in": False,
                "needs_captcha": True,
                "image": screenshot_b64,
                "message": "🔒 验证码后仍需处理，请查看新截图",
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"验证码处理异常: {str(e)[:100]}",
                "logged_in": False,
            }

    def _check_logged_in(self) -> bool:
        """检查当前页面是否已登录"""
        try:
            if not self.page:
                return False
            page = self.page
            current_url = page.url.lower()
            login_kw_in_url = ["login", "signin", "passport", "logon"]
            on_login_page = any(kw in current_url for kw in login_kw_in_url)

            cookies = self.context.cookies() if self.context else []
            auth_kw = self.platform_config.get("auth_cookie_keywords",
                                               ["auth", "token", "session", "sid", "uid"])
            has_auth_cookie = any(
                any(kw in c["name"].lower() for kw in auth_kw)
                for c in cookies
            )

            # 检查页面文本中的登录指示
            indicators = self.platform_config.get("logged_in_indicator", [])
            if indicators:
                try:
                    body = page.inner_text("body")[:2000]
                    for ind in indicators:
                        if ind in body:
                            return True
                except Exception:
                    pass

            # Cookie 检查（仅凭真实认证cookie判断，禁止cookie数量判据）
            if has_auth_cookie and not on_login_page:
                return True

            return False
        except Exception:
            return False

    def _detect_captcha(self) -> bool:
        """检测页面是否包含验证码元素"""
        try:
            if not self.page:
                return False
            page = self.page
            body = page.inner_text("body")[:500]
            captcha_kw = ["验证码", "captcha", "security code", "图形验证", "slide"]
            for kw in captcha_kw:
                if kw in body:
                    return True
            # 检查常见验证码元素
            captcha_selectors = [
                "img[src*='captcha']", "img[src*='seccode']",
                ".captcha", "#captcha", ".geetest", "#nc_1",
                ".slide-verify", ".tencent-captcha",
            ]
            for sel in captcha_selectors:
                try:
                    if page.query_selector(sel):
                        return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    def _get_cookie_string(self) -> str:
        """获取当前上下文的 Cookie 字符串"""
        try:
            if not self.context:
                return ""
            cookies = self.context.cookies()
            return "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        except Exception:
            return ""

    def take_screenshot(self) -> str:
        """获取当前页面截图（base64）"""
        try:
            if not self.page:
                return ""
            return base64.b64encode(self.page.screenshot(type="png", full_page=False)).decode()
        except Exception:
            return ""

    def close(self):
        """关闭浏览器"""
        self._cleanup_playwright()
        self.is_running = False

    def submit_text_captcha(self, captcha_code: str, platform: str = "") -> dict:
        """提交文本验证码 — 填入验证码输入框，点击提交按钮"""
        try:
            if not self.page:
                return {"success": False, "error": "浏览器未启动", "logged_in": False}

            page = self.page
            base_poll = self.platform_config if self.platform_config else LOGIN_PAGE_MAP.get(platform, {})

            # 1. 查找验证码输入框并填入代码
            captcha_selectors = [
                "input[name*='captcha']", "input[id*='captcha']",
                "input[placeholder*='验证码']", "input[placeholder*='captcha']",
                "input[type='text']:not([name*='user']):not([name*='login'])",
            ]
            filled = False
            for sel in captcha_selectors:
                try:
                    inp = page.wait_for_selector(sel, timeout=2000)
                    if inp and inp.is_visible():
                        inp.fill("")
                        time.sleep(0.3)
                        inp.type(captcha_code, delay=60)
                        filled = True
                        time.sleep(0.5)
                        break
                except:
                    continue

            if not filled:
                return {
                    "success": False,
                    "error": "未找到验证码输入框，请检查页面",
                    "logged_in": False,
                }

            # 2. 点击提交按钮
            sub_sel = base_poll.get("submit_selector", "button[type='submit']")
            try:
                submit_btn = page.wait_for_selector(sub_sel, timeout=5000)
                if submit_btn and submit_btn.is_visible():
                    submit_btn.click()
                else:
                    page.evaluate("document.querySelector('form')?.submit()")
            except:
                page.evaluate("document.querySelector('form')?.submit()")

            page.wait_for_timeout(5000)
            screenshot_b64 = self.take_screenshot()

            # 3. 检查登录结果
            logged_in = self._check_logged_in()
            if logged_in:
                cookies = self._get_cookie_string()
                return {
                    "success": True,
                    "logged_in": True,
                    "cookies": cookies,
                    "image": screenshot_b64,
                    "message": "✅ 登录成功！Cookie 已自动获取",
                }

            # 检查是否又出现验证码
            needs_captcha = self._detect_captcha()
            if needs_captcha:
                return {
                    "success": True,
                    "logged_in": False,
                    "needs_captcha": True,
                    "image": screenshot_b64,
                    "message": "验证码错误或需要新验证码",
                    "error": "验证码错误",
                }

            return {
                "success": True,
                "logged_in": False,
                "needs_captcha": False,
                "image": screenshot_b64,
                "message": "登录结果不确定，请查看截图",
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"验证码提交异常: {str(e)[:100]}",
                "logged_in": False,
            }

    def poll_login_result(self) -> dict:
        """轮询当前登录状态（验证码提交后的异步流程）"""
        try:
            if not self.page:
                return {"success": False, "error": "浏览器未启动", "logged_in": False}

            page = self.page
            screenshot_b64 = self.take_screenshot()

            # 检查登录状态
            logged_in = self._check_logged_in()
            if logged_in:
                cookies = self._get_cookie_string()
                return {
                    "logged_in": True,
                    "cookies": cookies,
                    "image": screenshot_b64,
                }

            # 检查是否需要新验证码
            needs_captcha = self._detect_captcha()
            if needs_captcha:
                return {
                    "needs_captcha": True,
                    "image": screenshot_b64,
                    "error": "需要新验证码",
                }

            # 仍在进行中
            return {
                "running": True,
                "image": screenshot_b64,
                "message": "登录进行中...",
            }

        except Exception as e:
            return {"running": False, "error": str(e)[:100]}
