"""阿莫论坛 Playwright 登录器 — 浏览器自动化登录

处理 amobbs 的特殊验证码（点击式"我不是机器人"复选框）：
1. Playwright 打开登录页面
2. 填入账号密码
3. 点击验证码复选框
4. 等待 ✓（通过）或 ✗（失败）
5. ✓ → 提交登录 → 保存 Cookie
6. ✗ → 重试

与 FS 后台验证码系统集成：验证码图片以 base64 返回给前端显示。
"""
import os, re, time, json, base64
from typing import Optional


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
    # 用 Playwright 的 API 查找
    try:
        import subprocess
        r = subprocess.run(
            ["python3", "-c", "import playwright; print(playwright.__path__[0])"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            pw_path = r.stdout.strip()
            browser_path = os.path.join(os.path.dirname(pw_path),
                "browsers", "chromium-1228", "chrome-linux64", "chrome")
            if os.path.isfile(browser_path):
                return browser_path
    except:
        pass
    return ""


class AmobbsPlaywrightLogin:
    """阿莫论坛 Playwright 登录器"""

    def __init__(self, site_url: str = ""):
        """初始化

        数据驱动：site_url 为空时从探索数据/账号配置读取"""
        self.site_url = (site_url or "").rstrip("/")
        if not self.site_url:
            # 从探索数据获取默认URL
            self.site_url = self._get_default_site_url()
        self.browser = None
        self.context = None
        self.page = None
        self._captcha_screenshot = None

    @staticmethod
    def _get_default_site_url() -> str:
        """数据驱动：从探索数据获取默认站点URL"""
        import os, json
        try:
            reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "platform_reports")
            for fname in os.listdir(reports_dir):
                if fname.endswith("_login_capabilities.json") and not fname.startswith("_"):
                    fpath = os.path.join(reports_dir, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("engine") == "discuz":
                        login_url = data.get("login_url", "")
                        if login_url and login_url.startswith("http"):
                            return login_url.rstrip("/member.php?mod=logging&action=login").rstrip("/login")
            return "https://www.amobbs.com"  # 最终回退
        except Exception:
            return "https://www.amobbs.com"



    def _ensure_browser(self):
        """确保浏览器已启动"""
        if self.browser and self.page:
            try:
                self.page.title()
                return
            except:
                pass
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        chrome_path = _find_chromium()
        if chrome_path:
            self.browser = self._pw.chromium.launch(
                headless=True,
                executable_path=chrome_path,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage", "--disable-gpu"],
            )
        else:
            self.browser = self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        self.page = self.context.new_page()

    def close(self):
        """关闭浏览器"""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, '_pw'):
                self._pw.stop()
        except:
            pass

    def take_screenshot(self, selector: str = None) -> str:
        """截图并返回 base64"""
        self._ensure_browser()
        if selector:
            try:
                el = self.page.wait_for_selector(selector, timeout=5000)
                screenshot = el.screenshot()
            except:
                screenshot = self.page.screenshot()
        else:
            screenshot = self.page.screenshot()
        return base64.b64encode(screenshot).decode()

    def login(self, username: str, password: str,
              captcha_provider: str = "manual") -> dict:
        """执行 Playwright 登录 amobbs

        返回:
            success: bool
            logged_in: bool   — 是否最终登录成功
            needs_captcha: bool — 是否需要验证码
            image: str        — 验证码截图（base64），需要时提供
            captcha_type: str — "checkbox" | "text" | "none"
            error: str
            cookies: list     — 登录成功的 cookie
        """
        try:
            self._ensure_browser()
            page = self.page

            # 1. 访问登录页
            login_url = f"{self.site_url}/member.php?mod=logging&action=login"
            page.goto(login_url, wait_until="networkidle", timeout=30000)
            time.sleep(1)

            # 2. 填入用户名密码
            try:
                username_input = page.wait_for_selector(
                    "input[name='username'], input#ls_username",
                    timeout=5000
                )
                username_input.fill("")
                time.sleep(0.3)
                username_input.type(username, delay=50)
            except Exception as e:
                return {"success": False, "logged_in": False,
                        "error": f"找不到用户名输入框: {e}"}

            try:
                pw_input = page.wait_for_selector(
                    "input[name='password'], input#ls_password",
                    timeout=5000
                )
                pw_input.fill("")
                time.sleep(0.3)
                pw_input.type(password, delay=50)
            except Exception as e:
                return {"success": False, "logged_in": False,
                        "error": f"找不到密码输入框: {e}"}

            # 3. 点击登录按钮（触发验证码）
            try:
                login_btn = page.wait_for_selector(
                    "button[name='loginsubmit'], "
                    "button:has-text('登录'), "
                    "input[name='loginsubmit'], "
                    "em:has-text('登录')",
                    timeout=5000
                )
                login_btn.click()
            except:
                # 可能已自动触发，尝试直接提交
                page.evaluate("""
                    document.querySelector('form[name="login"]')?.submit()
                """)

            time.sleep(2)

            # 4. 检查是否需要验证码
            page_content = page.content()

            # 检查是否有 seccode（文本验证码）
            seccode_img = page.query_selector("img[src*='seccode'], #seccode_image")
            # 检查是否有 reCAPTCHA 风格的验证码
            captcha_iframe = page.query_selector("iframe[src*='recaptcha'], iframe[src*='captcha']")
            # 检查是否有 check 框（amobbs 特有的点击验证）
            captcha_check = page.query_selector(
                ".mc_captcha, .captcha_check, "
                "[class*='captcha'], [id*='captcha'], "
                ".geetest, .nc-container"
            )

            if seccode_img or captcha_iframe or captcha_check:
                # 需要验证码 — 截取验证码区域的截图
                screenshot_b64 = self.take_screenshot()

                # 判断验证码类型
                if captcha_check:
                    captcha_type = "checkbox"
                elif seccode_img:
                    captcha_type = "text"
                else:
                    captcha_type = "recaptcha"

                return {
                    "success": True,
                    "logged_in": False,
                    "needs_captcha": True,
                    "image": screenshot_b64,
                    "captcha_type": captcha_type,
                    "error": "",
                    "message": f"需要{captcha_type}验证码，请处理后在后台确认",
                }

            # 5. 不需要验证码 — 检查是否已登录
            time.sleep(2)
            current_url = page.url
            cookies_list = context_cookies = self.context.cookies() if self.context else []

            # 检查登录成功标志
            is_logged_in = False
            auth_cookies = [c for c in cookies_list
                           if "auth" in c.get("name", "").lower()
                           or "sid" in c.get("name", "").lower()]
            if auth_cookies:
                is_logged_in = True
            # 禁止 cookie 数量判据（铁律 v4.55）

            if is_logged_in:
                cookie_str = "; ".join(
                    f"{c['name']}={c['value']}" for c in cookies_list
                    if c.get('name') and c.get('value')
                )
                return {
                    "success": True,
                    "logged_in": True,
                    "needs_captcha": False,
                    "cookies": cookie_str,
                    "error": "",
                }

            # 检查错误信息
            error_match = re.search(
                r'<div[^>]*class="alert_error"[^>]*>(.*?)</div>',
                page_content, re.DOTALL
            )
            error_msg = ""
            if error_match:
                error_msg = re.sub(r"<[^>]+>", "", error_match.group(1)).strip()
            if not error_msg:
                error_msg = "登录失败，未知原因"

            return {
                "success": False,
                "logged_in": False,
                "needs_captcha": False,
                "error": error_msg[:200],
            }

        except Exception as e:
            return {"success": False, "logged_in": False,
                    "error": f"Playwright 登录异常: {e}"}

    def click_captcha_and_submit(self) -> dict:
        """点击验证码复选框并提交登录

        处理 amobbs 特殊验证码行为：
        1. 点击复选框
        2. 等待 ✓ 或 ✗ 出现
        3. ✓ → 提交登录 → 返回 cookie
        4. ✗ → 返回重试

        返回同 login() 格式
        """
        try:
            self._ensure_browser()
            page = self.page

            # 1. 查找验证码元素并点击
            captcha_selectors = [
                ".mc_captcha",
                ".captcha_check",
                ".geetest_radar_tip",
                ".nc_scale",
                "iframe[src*='recaptcha']",
                "[class*='captcha']",
                "#captcha",
                ".captcha-container",
            ]

            clicked = False
            for sel in captcha_selectors:
                try:
                    el = page.wait_for_selector(sel, timeout=3000)
                    if el and el.is_visible():
                        el.click()
                        clicked = True
                        time.sleep(2)
                        break
                except:
                    continue

            if not clicked:
                # 尝试点击登录按钮附近的区域（可能点击登录按钮触发了验证码）
                try:
                    login_btn = page.wait_for_selector(
                        "button[name='loginsubmit'], input[name='loginsubmit']",
                        timeout=3000
                    )
                    login_btn.click()
                    time.sleep(2)
                except:
                    pass

            # 2. 等待验证码结果
            page_content = page.content()

            # 检查 ✓ - 验证通过
            checkmark_indicators = [
                "✓", "√", "check", "pass", "success",
                "已验证", "验证通过"
            ]
            cross_indicators = [
                "✗", "×", "fail", "error", "验证失败",
                "请重新验证"
            ]

            # 截图看当前状态
            screenshot_b64 = self.take_screenshot()

            # 检查是否出现了 reCAPTCHA 挑战（图片选择）
            challenge_iframe = page.query_selector(
                "iframe[src*='bframe'], iframe[title*='recaptcha']"
            )

            if challenge_iframe:
                return {
                    "success": True,
                    "needs_captcha": True,
                    "captcha_type": "recaptcha_challenge",
                    "image": screenshot_b64,
                    "message": "reCAPTCHA 图片挑战，请在浏览器中完成",
                    "logged_in": False,
                }

            # 检查验证结果
            has_checkmark = any(
                ind in page_content for ind in checkmark_indicators
            )
            has_cross = any(
                ind in page_content for ind in cross_indicators
            )

            if has_checkmark:
                # 验证通过 — 尝试提交登录
                try:
                    submit_btn = page.wait_for_selector(
                        "button[name='loginsubmit'], "
                        "input[name='loginsubmit'], "
                        "em:has-text('登录')",
                        timeout=5000
                    )
                    submit_btn.click()
                except:
                    page.evaluate("""
                        document.forms[0]?.submit()
                    """)

                time.sleep(3)

                # 检查登录状态
                cookies_list = self.context.cookies() if self.context else []
                auth_cookies = [c for c in cookies_list
                               if "auth" in c.get("name", "").lower()
                               or "sid" in c.get("name", "").lower()]

                if auth_cookies:
                    cookie_str = "; ".join(
                        f"{c['name']}={c['value']}" for c in cookies_list
                        if c.get('name') and c.get('value')
                    )
                    return {
                        "success": True,
                        "logged_in": True,
                        "needs_captcha": False,
                        "cookies": cookie_str,
                        "error": "",
                    }

                # 还没登录成功，可能还需要进一步验证
                return {
                    "success": True,
                    "needs_captcha": True,
                    "captcha_type": "additional_check",
                    "image": screenshot_b64,
                    "message": "验证码通过，但登录可能还需要额外步骤",
                    "logged_in": False,
                }

            elif has_cross:
                # 验证失败 — 返回截图让用户看
                return {
                    "success": True,
                    "needs_captcha": True,
                    "captcha_type": "checkbox_retry",
                    "image": screenshot_b64,
                    "message": "验证码未通过，请重试",
                    "logged_in": False,
                }

            # 不确定状态 — 截图给用户看
            return {
                "success": True,
                "needs_captcha": True,
                "captcha_type": "unknown",
                "image": screenshot_b64,
                "message": "无法确定验证码状态，请查看截图",
                "logged_in": False,
            }

        except Exception as e:
            return {"success": False, "logged_in": False,
                    "error": f"验证码处理异常: {e}"}

    def get_cookies(self) -> str:
        """获取当前浏览器的 cookie 字符串"""
        try:
            cookies_list = self.context.cookies() if self.context else []
            return "; ".join(
                f"{c['name']}={c['value']}" for c in cookies_list
                if c.get('name') and c.get('value')
            )
        except Exception as e:
            return ""

    def submit_text_captcha(self, captcha_code: str) -> dict:
        """提交文本验证码 — 填入验证码，点击边框区域触发核验 ✓，核验通过后提交登录

        Amobbs 特殊行为：
        1. 在验证码输入框填入代码
        2. 点击边框附近区域触发 ✓ 核验
        3. ✓ → 提交登录 → 返回 cookie
        4. ✗ → 返回重试
        """
        try:
            self._ensure_browser()
            page = self.page

            # 1. 查找验证码输入框并填入代码
            captcha_input_selectors = [
                "input[name='seccodeverify']",
                "input#seccodeverify",
                "input[name*='seccode']",
                "input[id*='seccode']",
                "input[placeholder*='验证码']",
                "input[name*='captcha']",
                "input[id*='captcha']",
            ]

            filled = False
            for sel in captcha_input_selectors:
                try:
                    inp = page.wait_for_selector(sel, timeout=2000)
                    if inp and inp.is_visible():
                        inp.fill("")
                        time.sleep(0.3)
                        inp.type(captcha_code, delay=80)
                        filled = True
                        time.sleep(0.5)
                        break
                except:
                    continue

            if not filled:
                # 没有找到验证码输入框，尝试直接提交
                return self.click_captcha_and_submit()

            # 2. 点击输入框附近区域触发 ✓ 核验
            # 点击验证码图片或验证码输入框边框区域
            try:
                captcha_img = page.query_selector("img[src*='seccode'], #seccode_image")
                if captcha_img:
                    box = captcha_img.bounding_box()
                    if box:
                        # 点击图片右侧空白区域（触发 √ 核验）
                        page.mouse.click(box['x'] + box['width'] + 10, box['y'] + box['height'] / 2)
                        time.sleep(2)
            except:
                # 点击输入框下面的空白区域
                try:
                    inp = page.query_selector("input[name='seccodeverify']") or \
                          page.query_selector("input[id*='captcha']")
                    if inp:
                        box = inp.bounding_box()
                        if box:
                            page.mouse.click(box['x'] + box['width'] + 5, box['y'] + box['height'] / 2)
                            time.sleep(2)
                except:
                    pass

            # 3. 检查 ✓ / ✗
            time.sleep(1)
            page_content = page.content()

            # 检查 ✓ (核验通过)
            checkmark_signals = ["✓", "√", "check", "pass", "success", "已验证", "验证通过"]
            cross_signals = ["✗", "×", "fail", "error", "验证失败", "请重新验证"]

            has_checkmark = any(s in page_content for s in checkmark_signals)
            has_cross = any(s in page_content for s in cross_signals)

            screenshot_b64 = self.take_screenshot()

            if has_checkmark:
                # ✓ 核验通过 — 提交登录
                try:
                    submit_btn = page.wait_for_selector(
                        "button[name='loginsubmit'], input[name='loginsubmit'], "
                        "em:has-text('登录'), button:has-text('登录')",
                        timeout=5000
                    )
                    if submit_btn:
                        submit_btn.click()
                except:
                    page.evaluate("document.forms[0]?.submit()")

                time.sleep(3)

                # 检查登录结果
                cookies_list = self.context.cookies() if self.context else []
                auth_cookies = [c for c in cookies_list
                               if "auth" in c.get("name", "").lower()
                               or "sid" in c.get("name", "").lower()]

                if auth_cookies:
                    cookie_str = "; ".join(
                        f"{c['name']}={c['value']}" for c in cookies_list
                        if c.get('name') and c.get('value')
                    )
                    return {
                        "success": True,
                        "logged_in": True,
                        "needs_captcha": False,
                        "cookies": cookie_str,
                        "captcha_verified": True,
                        "error": "",
                    }

                # 登录中但还未完成
                return {
                    "success": True,
                    "logged_in": False,
                    "captcha_verified": True,
                    "needs_captcha": False,
                    "image": screenshot_b64,
                    "message": "验证码核验通过 ✓，正在登录...",
                }

            elif has_cross:
                # ✗ 核验失败
                return {
                    "success": True,
                    "needs_captcha": True,
                    "captcha_type": "text",
                    "image": screenshot_b64,
                    "message": "验证码错误 ✗，请重新输入",
                    "error": "验证码错误",
                    "logged_in": False,
                }

            # 不确定状态 — 截图给用户看
            return {
                "success": True,
                "needs_captcha": True,
                "captcha_type": "unknown",
                "image": screenshot_b64,
                "message": "无法确定验证码状态，请查看截图",
                "logged_in": False,
            }

        except Exception as e:
            return {"success": False, "logged_in": False,
                    "error": f"验证码提交异常: {e}"}
