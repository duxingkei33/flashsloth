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
import os, re, time, json, base64, io, urllib.request, urllib.parse
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

    def __init__(self, site_url: str = "", platform: str = ""):
        """初始化

        数据驱动：site_url 为空时从探索数据/账号配置读取
        platform 参数：指定平台名（如 mydigit/discuz/amobbs），用于从 DB 读取 site_url"""
        self.site_url = (site_url or "").rstrip("/")
        self.platform = platform
        if not self.site_url:
            # 从探索数据获取默认URL（数据驱动，平台感知）
            self.site_url = self._get_default_site_url(platform)
        self.browser = None
        self.context = None
        self.page = None
        self._captcha_screenshot = None

    @staticmethod
    def _get_default_site_url(platform: str = "") -> str:
        """数据驱动：从 DB 探索表的 full_data 获取指定平台的 site_url

        优先从 platform_exploration 表的 full_data.site_url 读取，
        兜底读取 *_exploration_report.json 文件。
        Args:
            platform: 平台名（amobbs/mydigit/discuz 等），空字符串时兜底返回空
        Returns:
            site_url 字符串，末尾无斜杠
        """
        import os, json
        # 优先从 DB 读取（数据驱动 — 铁律#35）
        if platform:
            try:
                from flashsloth.core.database import get_db
                db = get_db()
                row = db.execute(
                    "SELECT full_data FROM platform_exploration WHERE platform=?",
                    (platform,)
                ).fetchone()
                db.close()
                if row:
                    fd = row["full_data"]
                    if isinstance(fd, str):
                        fd = json.loads(fd)
                    if isinstance(fd, dict):
                        site_url = fd.get("site_url", "")
                        if site_url:
                            return site_url.rstrip("/")
            except Exception:
                pass
        # 兜底：从 *_exploration_report.json 读取（兼容旧数据）
        try:
            reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "platform_reports")
            json_name = platform if platform else "amobbs"
            report_path = os.path.join(reports_dir, f"{json_name}_exploration_report.json")
            if os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    site_url = data.get("site_url", "")
                    if site_url:
                        return site_url.rstrip("/")
        except Exception:
            pass
        return ""  # 空字符串 — 由调用方自行处理



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
                      "--disable-dev-shm-usage", "--disable-gpu",
                      "--ignore-certificate-errors"],
            )
        else:
            self.browser = self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--ignore-certificate-errors"],
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

    def _get_captcha_image(self) -> dict:
        """提取验证码图片 — 使用 Playwright 元素截图（带会话 Cookie）

        返回:
            image: str — base64 编码的图片
            captcha_image_url: str — 原始图片 URL（有的话）
        """
        result = {"image": "", "captcha_image_url": ""}
        try:
            page = self.page
            img_selectors = [
                "img[src*='seccode']",
                "#seccode_image",
                "img[id*='seccode']",
            ]
            for sel in img_selectors:
                try:
                    img_el = page.query_selector(sel)
                    if img_el:
                        src = img_el.get_attribute("src") or ""
                        result["captcha_image_url"] = src
                        # 使用 Playwright 元素截图（带会话 Cookie，比 urllib 可靠）
                        screenshot = img_el.screenshot()
                        result["image"] = base64.b64encode(screenshot).decode()
                        return result
                except Exception:
                    continue
        except Exception:
            pass
        # 降级到全页截图
        try:
            result["image"] = self.take_screenshot()
        except Exception:
            pass
        return result

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

            # 3. 展开表单（Discuz 登录表单默认折叠，验证码输入框不可见）
            #    需要点击「用户名」标签（span.login_slct）展开完整表单
            try:
                captcha_input_check = page.query_selector("input[name='seccodeverify']")
                if not captcha_input_check or not captcha_input_check.is_visible():
                    form_toggle = page.wait_for_selector("span.login_slct", timeout=3000)
                    if form_toggle and form_toggle.is_visible():
                        form_toggle.click()
                        time.sleep(0.5)
            except:
                pass

            # 4. 数据驱动：检查是否需要验证码
            # 优先从探索数据判断（铁律#28），兜底 DOM 检测
            _needs_captcha_check = True
            if self.platform:
                try:
                    import sqlite3, json as _json
                    db = sqlite3.connect('flashsloth.db')
                    row = db.execute("SELECT captcha_info FROM platform_exploration WHERE platform=?", (self.platform,)).fetchone()
                    db.close()
                    if row:
                        ci = _json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
                        if ci.get('has_captcha') is False:
                            _needs_captcha_check = False
                except:
                    pass

            if _needs_captcha_check:
                # 只在探索数据说"需要验证码"时检查页面元素
                seccode_input = page.query_selector("input[name='seccodeverify']")
                seccode_img = page.query_selector("img[src*='seccode'], #seccode_image")
                captcha_iframe = page.query_selector("iframe[src*='recaptcha'], iframe[src*='captcha']")
                captcha_check = page.query_selector(
                    ".mc_captcha, .captcha_check, "
                    "[class*='captcha'], [id*='captcha'], "
                    ".geetest, .nc-container"
                )
            else:
                seccode_input = seccode_img = captcha_iframe = captcha_check = None

            if seccode_img or seccode_input or captcha_iframe or captcha_check:
                # 需要验证码 — 从 img src 提取验证码图片（不提交表单！）
                captcha_result = self._get_captcha_image()
                screenshot_b64 = captcha_result.get("image", "")
                captcha_image_url = captcha_result.get("captcha_image_url", "")

                # 判断验证码类型
                if seccode_img or seccode_input:
                    captcha_type = "text"
                elif captcha_check:
                    captcha_type = "checkbox"
                else:
                    captcha_type = "recaptcha"

                return {
                    "success": True,
                    "logged_in": False,
                    "needs_captcha": True,
                    "image": screenshot_b64,
                    "captcha_image_url": captcha_image_url,
                    "captcha_type": captcha_type,
                    "error": "",
                    "message": f"需要{captcha_type}验证码，请处理后在后台确认",
                }

            # 5. 不需要验证码 — 提交登录表单（确保 formhash CSRF 令牌被提交）
            try:
                login_btn = page.wait_for_selector(
                    "button[name='loginsubmit'], "
                    "button:has-text('登录'), "
                    "input[name='loginsubmit'], "
                    "em:has-text('登录')",
                    timeout=3000
                )
                if login_btn and login_btn.is_visible():
                    login_btn.click()
                else:
                    # 按钮不可见，用 JS 点击按钮（触发 onclick 事件）
                    page.evaluate("document.querySelector('button[name=loginsubmit]')?.click()")
            except:
                # 所有方式失败，直接用 JS 提交表单（包含 formhash）
                page.evaluate("document.querySelector('form[name=login]')?.submit()")

            time.sleep(2)

            # 6. 检查登录结果
            current_url = page.url
            cookies_list = self.context.cookies() if self.context else []
            page_content = page.content()

            # 检查登录成功标志
            is_logged_in = False
            auth_cookies = [c for c in cookies_list
                           if "auth" in c.get("name", "").lower()
                           or "sid" in c.get("name", "").lower()]
            if auth_cookies:
                is_logged_in = True

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

            # 检查错误信息 — 数据驱动：先找 Discuz 标准错误 div，再找其他常见错误元素
            error_msg = ""
            # 尝试多种方式提取错误信息
            error_selectors = [
                "div.alert_error", "div.alert-danger", "div.error",
                "div[class*='error']", "div[class*='alert']",
                ".show_error", "#error_msg"
            ]
            for sel in error_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        error_msg = el.inner_text().strip()
                        if error_msg:
                            break
                except:
                    continue
            if not error_msg:
                # 检查页面是否有登录失败特征
                if "password" in page_content.lower() and "login" in current_url.lower():
                    error_msg = "登录失败：密码错误或账号不存在"
                elif "登录" in page_content:
                    error_msg = "登录失败：请检查账号密码是否正确"
                else:
                    error_msg = "登录失败：页面已跳转，请检查账号密码"

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
        """提交文本验证码 — 填入验证码，点击输入框边框触发核验 ✓，核验通过后提交登录

        Amobbs 特殊行为（使用 DOM 元素 class 判断验证码核验状态）：
        1. 在验证码输入框填入代码
        2. 点击输入框边框附近区域触发 ✓ 核验
        3. 通过 `.seccodecheck` 元素的 class 变化判断 ✓/✗
        4. ✓ → 提交登录 → 返回 cookie
        5. ✗ → 返回重试
        """
        try:
            self._ensure_browser()
            page = self.page

            # 0. 展开表单（确保验证码输入框可见）— 快速检查，无等待
            try:
                captcha_input = page.query_selector("input[name='seccodeverify']")
                if not captcha_input or not captcha_input.is_visible():
                    form_toggle = page.query_selector("span.login_slct")
                    if form_toggle and form_toggle.is_visible():
                        form_toggle.click()
            except:
                pass

            # 1. 查找验证码输入框并填入代码 — 直接只用 input[name='seccodeverify']，无 timeout 循环
            inp = page.query_selector("input[name='seccodeverify']")
            if not inp or not inp.is_visible():
                # 没有找到验证码输入框，尝试直接提交
                return self.click_captcha_and_submit()

            inp.fill("")
            inp.type(captcha_code, delay=80)

            # 2. 点击验证码输入框右边框区域触发 ✓ 核验 — 直接通过查询到的元素
            box = inp.bounding_box()
            if box:
                page.mouse.click(
                    box['x'] + box['width'] + 10,
                    box['y'] + box['height'] / 2
                )

            # 3. 等待验证码核验结果 — 短 timeout
            try:
                page.wait_for_selector(".seccodecheck", timeout=1000)
            except:
                pass

            # 检查 ✓ 核验通过 — .seccodecheck 元素是否有 seccodecheck_ok class
            try:
                seccode_ok = page.eval_on_selector(
                    ".seccodecheck",
                    "el => el.classList.contains('seccodecheck_ok')"
                )
                if seccode_ok:
                    # ✓ 核验通过 — 提交登录
                    try:
                        submit_btn = page.query_selector(
                            "button[name='loginsubmit'], input[name='loginsubmit'], "
                            "em:has-text('登录'), button:has-text('登录')"
                        )
                        if submit_btn:
                            submit_btn.click()
                    except:
                        page.evaluate("document.forms[0]?.submit()")

                    # 等待页面跳转/Cookie更新 — 先查已有 cookies，没有再等
                    cookies_list = self.context.cookies() if self.context else []
                    has_auth = any(
                        "auth" in c.get("name", "").lower() or "sid" in c.get("name", "").lower()
                        for c in cookies_list
                    )
                    if not has_auth:
                        try:
                            page.wait_for_function(
                                "() => document.cookie.includes('auth') || document.cookie.includes('sid')",
                                timeout=3000
                            )
                        except:
                            pass

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
                        "message": "验证码核验通过 ✓，正在登录...",
                    }
            except:
                pass

            # 检查 ✗ 核验失败 — .seccodecheck 元素是否有 seccodecheck_err class
            try:
                seccode_err = page.eval_on_selector(
                    ".seccodecheck",
                    "el => el.classList.contains('seccodecheck_err')"
                )
                if seccode_err:
                    return {
                        "success": True,
                        "needs_captcha": True,
                        "captcha_type": "text",
                        "message": "验证码错误 ✗，请重新输入",
                        "error": "验证码错误",
                        "logged_in": False,
                    }
            except:
                pass

            # 兜底：用 page.content() 全文搜索 ✓/✗（仅在 DOM class 检测失败时）
            page_content = page.content()
            checkmark_signals = ["✓", "√", "check", "pass", "success", "已验证", "验证通过"]
            cross_signals = ["✗", "×", "fail", "error", "验证失败", "请重新验证"]

            has_checkmark = any(s in page_content for s in checkmark_signals)
            has_cross = any(s in page_content for s in cross_signals)

            if has_checkmark:
                # ✓ 核验通过 — 尝试提交登录
                try:
                    submit_btn = page.query_selector(
                        "button[name='loginsubmit'], input[name='loginsubmit'], "
                        "em:has-text('登录'), button:has-text('登录')"
                    )
                    if submit_btn:
                        submit_btn.click()
                except:
                    page.evaluate("document.forms[0]?.submit()")

                # 先查已有 cookies
                cookies_list = self.context.cookies() if self.context else []
                has_auth = any(
                    "auth" in c.get("name", "").lower() or "sid" in c.get("name", "").lower()
                    for c in cookies_list
                )
                if not has_auth:
                    try:
                        page.wait_for_function(
                            "() => document.cookie.includes('auth') || document.cookie.includes('sid')",
                            timeout=3000
                        )
                    except:
                        pass

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

                return {
                    "success": True,
                    "logged_in": False,
                    "captcha_verified": True,
                    "needs_captcha": False,
                    "message": "验证码核验通过 ✓，正在登录...",
                }

            elif has_cross:
                return {
                    "success": True,
                    "needs_captcha": True,
                    "captcha_type": "text",
                    "message": "验证码错误 ✗，请重新输入",
                    "error": "验证码错误",
                    "logged_in": False,
                }

            # 不确定状态
            screenshot_b64 = self._get_captcha_image().get("image", "")
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
