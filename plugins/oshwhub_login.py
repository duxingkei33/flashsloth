"""OSHWHub (立创开源硬件平台) Playwright 登录器 — 浏览器自动化登录

oshwhub.com 是嘉立创 EDA 生态的一部分，Next.js + Ant Design 构建。
登录页面由 JS 客户端渲染，使用 Playwright 模拟真实浏览器操作。

处理流程：
1. Playwright 打开 https://oshwhub.com/login
2. 等待 Ant Design 表单渲染完成
3. 填入账号密码（支持邮箱/用户名）
4. 检测并处理验证码（接口返回 418 时走手动验证码流程）
5. 提交登录
6. 登录成功后获取 Cookie 并保存

与 FS 后台验证码系统集成：验证码截图以 base64 返回给前端显示。
"""
import os, re, time, json, base64, random
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


def _human_delay(min_s: float = 0.5, max_s: float = 2.0):
    """人机延迟模拟"""
    time.sleep(random.uniform(min_s, max_s))


class OshwhubPlaywrightLogin:
    """OSHWHub 立创开源硬件平台 Playwright 登录器

    使用真实浏览器模拟登录 oshwhub.com。
    Next.js + Ant Design，表单由 JS 客户端渲染。
    """

    def __init__(self, site_url: str = "https://oshwhub.com"):
        self.site_url = site_url.rstrip("/")
        self.browser = None
        self.context = None
        self.page = None
        self._captcha_screenshot = None

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
                      "--disable-blink-features=AutomationControlled",
                      "--ignore-certificate-errors"],
            )
        else:
            self.browser = self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-blink-features=AutomationControlled",
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
        # 注入反自动化检测脚本（绕过浏览器特征识别）
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
            window.chrome = { runtime: {} };
        """)

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

    # ─────────────────────────────────────────────────────────
    # 数据驱动：从探索JSON读取表单选择器（铁律#19）
    # ─────────────────────────────────────────────────────────
    def _load_form_selectors(self) -> dict:
        """从探索JSON读取密码登录表单选择器（数据驱动，不硬编码）

        读取 platform_reports/oshwhub_exploration_report.json 中
        login_methods[password].form_selectors 字段。

        Returns:
            dict — Ant Design 选择器字典，空 dict 表示无数据
        """
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        report_path = os.path.join(base_dir, "platform_reports",
                                   "oshwhub_exploration_report.json")
        if not os.path.exists(report_path):
            return {}
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for method in data.get("login_methods", []):
                if method.get("method") == "password":
                    fs = method.get("form_selectors", {})
                    if fs:
                        return fs
        except Exception:
            pass
        return {}

    def _wait_for_login_form(self, timeout: int = 15000) -> bool:
        """等待登录表单渲染完成

        oshwhub 使用嘉立创统一登录（passport.jlc.com），
        目前使用 Ant Design 框架渲染表单。
        优先从探索JSON读取选择器（数据驱动，铁律#19），
        然后回退到通用选择器。
        """
        # 数据驱动：从探索JSON读取表单选择器
        form_selectors = self._load_form_selectors()
        antd_input = form_selectors.get("input_class", "input.ant-input")
        antd_container = form_selectors.get("input_container", ".ant-form-item")

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout)

            # ── Ant Design 选择器（数据驱动，铁律#19）──
            try:
                el = self.page.wait_for_selector(antd_input, timeout=3000)
                if el and el.is_visible():
                    return True
            except:
                pass

            # Ant Design form-item 容器检测
            antd_inputs = self.page.query_selector_all(f"{antd_container} input")
            if len(antd_inputs) >= 2:
                return True

            # ── Element UI / 通用选择器（fallback）──
            input_selectors = [
                "input.el-input__inner",
                "input[placeholder*='手机号码']",
                "input[placeholder*='邮箱']",
                "input[placeholder*='账号']",
                "input[placeholder*='密码']",
                "input[type='text']",
                "input[type='email']",
            ]
            for sel in input_selectors:
                try:
                    el = self.page.wait_for_selector(sel, timeout=3000)
                    if el and el.is_visible():
                        return True
                except:
                    continue

            # 检测 Element UI 表单容器
            form_items = self.page.query_selector_all(".el-input")
            if len(form_items) >= 2:
                return True

            return False
        except Exception:
            return False

    def _find_input_by_placeholder(self, page, keywords: list) -> Optional[object]:
        """根据 placeholder 关键字查找输入框"""
        for kw in keywords:
            try:
                el = page.query_selector(f"input[placeholder*='{kw}']")
                if el and el.is_visible():
                    return el
            except:
                pass
        return None

    def _detect_captcha(self) -> dict:
        """检测登录页面是否需要验证码

        OSHWHub 可能使用以下验证方式：
        1. 图形验证码（图片显示在表单中）
        2. 阿里云滑块验证码（nc-container）
        3. reCAPTCHA
        4. 无验证码

        返回:
            has_captcha: bool
            captcha_type: str — "image" | "slider" | "recaptcha" | "none"
            image: str — 截图 base64（仅当 type=image 时）
        """
        page = self.page
        try:
            page_content = page.content()

            # 检测图片验证码
            captcha_img = page.query_selector(
                "img[src*='captcha'], img[src*='verify'], "
                "img[src*='seccode'], .captcha-img img, "
                ".ant-form-item img[src*='code'], "
                "img[alt*='验证码'], img[alt*='captcha']"
            )

            # 检测滑块验证码（阿里云/极验）
            slider = page.query_selector(
                ".aliyun-captcha, #aliyunCaptcha-sliding-wrapper, "
                ".nc-container, .geetest, .captcha-slider, "
                "[class*='slider'], [id*='nc_'], "
                ".aliyun-slider, .slide-verify, "
                ".captcha-popup"
            )

            # 检测 reCAPTCHA
            recaptcha = page.query_selector(
                "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
                ".g-recaptcha, .h-captcha"
            )

            if captcha_img:
                screenshot_b64 = self.take_screenshot()
                return {
                    "has_captcha": True,
                    "captcha_type": "image",
                    "image": screenshot_b64,
                }
            elif slider:
                return {
                    "has_captcha": True,
                    "captcha_type": "slider",
                    "image": self.take_screenshot(),
                }
            elif recaptcha:
                return {
                    "has_captcha": True,
                    "captcha_type": "recaptcha",
                    "image": self.take_screenshot(),
                }

            return {"has_captcha": False, "captcha_type": "none", "image": ""}
        except Exception as e:
            return {"has_captcha": False, "captcha_type": "none", "image": ""}

    def _solve_aliyun_slider(self, page) -> bool:
        """自动解决阿里云滑块验证码

        使用 easeInOutCubic 缓动函数模拟人类拖拽轨迹，
        配合 Y 轴自然抖动绕过反爬检测。

        Returns:
            True 表示滑块验证通过，False 表示失败
        """
        try:
            slider = page.query_selector("#aliyunCaptcha-sliding-slider")
            if not slider or not slider.is_visible():
                return False

            # 获取滑块和滑动轨道位置
            box = slider.bounding_box()
            body = page.query_selector("#aliyunCaptcha-sliding-body")
            body_box = body.bounding_box() if body else None
            if not box or not body_box:
                return False

            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2
            # 目标：滑块右边缘对齐容器右边缘（留一点边距）
            end_x = body_box["x"] + body_box["width"] - 16
            distance = end_x - start_x
            if distance < 20:
                return False

            # ── 执行人性化拖拽 ──
            page.mouse.move(start_x, start_y)
            _human_delay(0.3, 0.6)
            page.mouse.down()
            time.sleep(random.uniform(0.1, 0.25))

            # 分段拖拽：使用 easeInOutCubic 缓动 + Y轴抖动
            total_steps = random.randint(55, 70)
            for i in range(1, total_steps + 1):
                t = i / total_steps
                # easeInOutCubic
                if t < 0.5:
                    eased = 4 * t * t * t
                else:
                    eased = 1 - (-2 * t + 2) ** 3 / 2

                x = start_x + distance * eased
                y_jitter = random.uniform(-3, 3)
                page.mouse.move(x, start_y + y_jitter)
                time.sleep(random.uniform(0.008, 0.025))

            page.mouse.up()
            time.sleep(2.0)

            # 检查滑块是否消失（验证通过）
            still_slider = page.query_selector("#aliyunCaptcha-sliding-slider")
            if still_slider and still_slider.is_visible():
                # 可能提示"拖动速度过快"或"请重试"，尝试第二次
                tips = page.query_selector(".captcha-popup__tips")
                if tips:
                    _human_delay(1.0, 2.0)
                    # 更慢的第二次尝试
                    page.mouse.move(start_x, start_y)
                    _human_delay(0.5, 0.8)
                    page.mouse.down()
                    time.sleep(random.uniform(0.15, 0.3))
                    total_steps = random.randint(70, 90)
                    for i in range(1, total_steps + 1):
                        t = i / total_steps
                        if t < 0.5:
                            eased = 4 * t * t * t
                        else:
                            eased = 1 - (-2 * t + 2) ** 3 / 2
                        x = start_x + distance * eased
                        y_jitter = random.uniform(-4, 4)
                        page.mouse.move(x, start_y + y_jitter)
                        time.sleep(random.uniform(0.015, 0.035))
                    page.mouse.up()
                    time.sleep(2.0)
                    still_slider = page.query_selector("#aliyunCaptcha-sliding-slider")
                    if still_slider and still_slider.is_visible():
                        return False
                return False

            return True
        except Exception:
            return False

    def _fill_login_form(self, page, username: str, password: str) -> bool:
        """智能填写登录表单

        优先从探索JSON读取 Ant Design 选择器（数据驱动，铁律#19），
        然后回退到 Element UI / 通用选择器。
        """
        # 数据驱动：从探索JSON读取表单选择器
        form_selectors = self._load_form_selectors()
        antd_username_sel = form_selectors.get("username", [])
        antd_password_sel = form_selectors.get("password", [])
        antd_input_class = form_selectors.get("input_class", "input.ant-input")

        # ── 用户名/邮箱/手机号输入框 ──
        username_filled = False

        # Ant Design 选择器（数据驱动）
        for sel in antd_username_sel:
            try:
                inp = page.query_selector(sel)
                if inp and inp.is_visible():
                    inp.click()
                    _human_delay(0.2, 0.5)
                    inp.fill("")
                    _human_delay(0.1, 0.3)
                    for char in username:
                        inp.type(char, delay=random.randint(40, 120))
                    username_filled = True
                    break
            except:
                continue

        if not username_filled:
            # Ant Design 通用：第一个可见的非密码 input.ant-input
            try:
                all_inputs = page.query_selector_all(antd_input_class)
                if all_inputs:
                    for inp in all_inputs:
                        tp = inp.get_attribute("type") or ""
                        if tp != "password" and inp.is_visible():
                            inp.click()
                            _human_delay(0.2, 0.5)
                            inp.fill("")
                            _human_delay(0.1, 0.3)
                            for char in username:
                                inp.type(char, delay=random.randint(40, 120))
                            username_filled = True
                            break
            except:
                pass

        if not username_filled:
            # Element UI
            try:
                all_inputs = page.query_selector_all("input.el-input__inner")
                if all_inputs:
                    for inp in all_inputs:
                        tp = inp.get_attribute("type") or ""
                        if tp != "password" and inp.is_visible():
                            inp.click()
                            _human_delay(0.2, 0.5)
                            inp.fill("")
                            _human_delay(0.1, 0.3)
                            for char in username:
                                inp.type(char, delay=random.randint(40, 120))
                            username_filled = True
                            break
            except:
                pass

        if not username_filled:
            # 尝试通用选择器
            username_selectors = [
                "input[placeholder*='手机号码']",
                "input[placeholder*='邮箱']",
                "input[placeholder*='账号']",
                "input:not([type='hidden']):not([type='password']):not([type='checkbox'])",
            ]
            for sel in username_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        _human_delay(0.2, 0.5)
                        el.fill("")
                        _human_delay(0.1, 0.3)
                        for char in username:
                            el.type(char, delay=random.randint(40, 120))
                        username_filled = True
                        break
                except:
                    continue

        _human_delay(0.5, 1.0)

        # ── 密码输入框 ──
        password_filled = False

        # Ant Design 选择器（数据驱动）
        for sel in antd_password_sel:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    _human_delay(0.2, 0.5)
                    el.fill("")
                    _human_delay(0.1, 0.3)
                    for char in password:
                        el.type(char, delay=random.randint(40, 120))
                    password_filled = True
                    break
            except:
                continue

        if not password_filled:
            password_selectors = [
                "input.el-input__inner[type='password']",
                "input[type='password']",
                "input[placeholder*='密码']",
            ]
            for sel in password_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.click()
                        _human_delay(0.2, 0.5)
                        el.fill("")
                        _human_delay(0.1, 0.3)
                        for char in password:
                            el.type(char, delay=random.randint(40, 120))
                        password_filled = True
                        break
                except:
                    continue

        return username_filled and password_filled

    def _find_submit_button(self, page):
        """查找登录/提交按钮"""
        submit_selectors = [
            "button.el-button--primary",
            "button[type='submit']",
            "button:has-text('登录')",
            "button:has-text('登 录')",
            "button:has-text('登入')",
            "button:has-text('Sign In')",
            "button.ant-btn-primary",
            "button.submit-btn",
            "input[type='submit']",
            "input[value*='登录']",
            "button[id*='login']",
        ]
        for sel in submit_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    return btn
            except:
                continue
        return None

    def _check_cookies_logged_in(self) -> bool:
        """检查 Cookie 中是否有登录凭证（统一委派到 cookie_validator）"""
        try:
            cookies_list = self.context.cookies() if self.context else []
            from flashsloth.core.cookie_validator import verify_cookie
            result = verify_cookie("oshwhub", cookies_list, input_type="list", phase="keyword")
            return result.get("valid", False)
        except Exception:
            return False

    def _get_cookie_string(self) -> str:
        """获取 cookie 字符串"""
        try:
            cookies_list = self.context.cookies() if self.context else []
            return "; ".join(
                f"{c['name']}={c['value']}" for c in cookies_list
                if c.get('name') and c.get('value')
            )
        except:
            return ""

    def _get_cookies_json(self) -> str:
        """获取结构化 cookies_json（保留 domain/path/secure，铁律#19）

        JLC SSO 需要 cookies_json 而非扁平字符串，
        Playwright cookies 对象含 name/value/domain/path/secure/httpOnly/sameSite。
        """
        try:
            cookies_list = self.context.cookies() if self.context else []
            return json.dumps(cookies_list)
        except:
            return ""

    def login(self, username: str, password: str,
              captcha_provider: str = "manual") -> dict:
        """执行 Playwright 登录 oshwhub.com

        参数:
            username: 邮箱或用户名
            password: 登录密码
            captcha_provider: 验证码处理方式 ("manual" | "auto")

        返回:
            success: bool          — 操作是否成功（含验证码重试）
            logged_in: bool        — 是否最终登录成功
            needs_captcha: bool    — 是否需要验证码
            image: str             — 验证码截图（base64），需要时提供
            captcha_type: str      — "image" | "slider" | "recaptcha" | "none"
            error: str
            cookies: str           — 登录成功的 cookie 字符串（扁平，向后兼容）
            cookies_json: str      — 结构化 cookies JSON（保留 domain/path/secure，
                                      JLC SSO 必需，铁律#19）
        """
        try:
            self._ensure_browser()
            page = self.page

            # ── 1. 访问登录页（嘉立创统一登录 passport.jlc.com）──
            login_url = f"{self.site_url}/login"
            # oshwhub.com 有 Cloudflare WAF，改用嘉立创统一登录
            # 检测是否 passport.jlc.com 域名
            if "passport" not in self.site_url:
                login_url = "https://passport.jlc.com/login"
            # 使用 domcontentloaded 而非 networkidle — passport.jlc.com 有广告/tracking
            # iframe 导致 networkidle 永不超时
            page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
            _human_delay(2.0, 3.0)

            # 尝试点击"账号登录"标签（Element UI 标签页）
            try:
                account_tab = page.query_selector("button:has-text('账号登录')")
                if account_tab and account_tab.is_visible():
                    account_tab.click()
                    _human_delay(0.5, 1.0)
            except:
                pass

            # ── 2. 等待表单渲染 ──
            form_ready = self._wait_for_login_form(timeout=15000)
            if not form_ready:
                # 可能已经跳转（已登录状态）
                if self._check_cookies_logged_in():
                    return {
                        "success": True, "logged_in": True,
                        "needs_captcha": False,
                        "cookies": self._get_cookie_string(),
                        "cookies_json": self._get_cookies_json(),
                        "error": "",
                        "message": "already_logged_in",
                    }
                # 截图看看当前状态
                screenshot_b64 = self.take_screenshot()
                return {
                    "success": False, "logged_in": False,
                    "needs_captcha": False,
                    "error": "登录表单未渲染完成（可能被 WAF 拦截或需等待 JS 加载）",
                    "image": screenshot_b64,
                }

            # ── 3. 检查验证码（提交前检测） ──
            captcha_info = self._detect_captcha()
            if captcha_info["has_captcha"]:
                # 如果是阿里云滑块，自动解决
                if captcha_info["captcha_type"] == "slider":
                    solved = self._solve_aliyun_slider(page)
                    if solved:
                        _human_delay(1.0, 2.0)
                    else:
                        return {
                            "success": True,
                            "logged_in": False,
                            "needs_captcha": True,
                            "image": captcha_info.get("image", ""),
                            "captcha_type": "slider",
                            "error": "阿里云滑块自动验证失败，需要手动处理",
                        }
                else:
                    return {
                        "success": True,
                        "logged_in": False,
                        "needs_captcha": True,
                        "image": captcha_info.get("image", ""),
                        "captcha_type": captcha_info["captcha_type"],
                        "error": "",
                        "message": f"需要{captcha_info['captcha_type']}验证码，请处理后在后台确认",
                    }

            # ── 4. 填入账号密码 ──
            filled = self._fill_login_form(page, username, password)
            if not filled:
                return {
                    "success": False, "logged_in": False,
                    "needs_captcha": False,
                    "error": "无法定位登录输入框（表单结构与预期不符）",
                    "image": self.take_screenshot(),
                }

            _human_delay(0.5, 1.5)

            # ── 5. 点击登录按钮 ──
            login_btn = self._find_submit_button(page)
            if login_btn:
                login_btn.click()
            else:
                # 尝试用键盘 Enter 提交
                page.keyboard.press("Enter")

            _human_delay(2.0, 3.0)

            # ── 6. 等待验证码弹出或登录结果 ──
            _human_delay(1.0, 1.5)

            # ── 7. 检查是否需要阿里云滑块验证码（提交后才弹出） ──
            captcha_after = self._detect_captcha()
            if captcha_after["has_captcha"]:
                if captcha_after["captcha_type"] == "slider":
                    solved = self._solve_aliyun_slider(page)
                    if solved:
                        _human_delay(2.0, 3.0)
                    else:
                        return {
                            "success": True,
                            "logged_in": False,
                            "needs_captcha": True,
                            "image": captcha_after.get("image", ""),
                            "captcha_type": "slider",
                            "error": "提交后阿里云滑块自动验证失败",
                        }
                else:
                    return {
                        "success": True,
                        "logged_in": False,
                        "needs_captcha": True,
                        "image": captcha_after.get("image", ""),
                        "captcha_type": captcha_after["captcha_type"],
                        "error": "",
                        "message": f"提交后检测到{captcha_after['captcha_type']}验证码，请处理",
                    }

            # ── 8. 检查登录成功 ──
            if self._check_cookies_logged_in():
                # 登录成功，额外访问 oshwhub.com 获取专属 Cookie
                try:
                    page.goto("https://oshwhub.com", wait_until="domcontentloaded", timeout=20000)
                    _human_delay(2.0, 3.0)
                except Exception as e:
                    print(f"oshwhub.com 导航失败（不影响核心登录Cookie）: {e}")
                cookie_str = self._get_cookie_string()
                return {
                    "success": True,
                    "logged_in": True,
                    "needs_captcha": False,
                    "cookies": cookie_str,
                    "cookies_json": self._get_cookies_json(),
                    "error": "",
                    "message": "login_success",
                }

            # ── 9. 检查错误信息（登录失败） ──
            page_content = page.content()

            # 从 Ant Design 消息提示中提取错误
            error_msg = self._extract_error_message(page_content)

            # 检查是否跳转到了首页（登录成功标志）
            current_url = page.url
            if "login" not in current_url.lower() and self.site_url.rstrip("/") in current_url:
                # 可能已登录成功
                if self._check_cookies_logged_in():
                    return {
                        "success": True,
                        "logged_in": True,
                        "needs_captcha": False,
                        "cookies": self._get_cookie_string(),
                        "cookies_json": self._get_cookies_json(),
                        "error": "",
                        "message": "login_redirect_success",
                    }
                else:
                    return {
                        "success": True,
                        "logged_in": True,
                        "needs_captcha": False,
                        "cookies": self._get_cookie_string(),
                        "cookies_json": self._get_cookies_json(),
                        "error": "",
                        "message": "redirect_no_auth_cookie_but_redirected",
                    }

            if not error_msg:
                error_msg = "登录失败，未知原因（可能账号密码错误、被 WAF 拦截或需验证码）"

            return {
                "success": False,
                "logged_in": False,
                "needs_captcha": False,
                "error": error_msg[:300],
                "image": self.take_screenshot(),
            }

        except Exception as e:
            return {"success": False, "logged_in": False,
                    "error": f"Playwright 登录异常: {e}"}

    def _extract_error_message(self, html: str) -> str:
        """从页面中提取错误信息

        OSHWHub 使用 Ant Design 组件显示错误，常见模式：
        1. message.error() — 浮动通知
        2. Form.Item 校验错误 — 表单字段下的红色提示
        3. JSON API 响应中的 error 字段
        """
        # 检查 Ant Design message 提示（可能在页面文本中）
        error_patterns = [
            # 常见中文错误
            r"(?:密码错误|账号错误|登录失败|用户名不存在|"
            r"账号不存在|用户不存在|验证码错误|验证码已过期|"
            r"登录频繁|操作频繁|账号被锁定|账号已被锁定|"
            r"密码不正确|用户名或密码错误)",
            # JSON 错误（API 返回）
            r'"error"\s*:\s*"([^"]+)"',
            r'"message"\s*:\s*"([^"]+)"',
            # 页面文本
            r'<div[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</div>',
            r'<span[^>]*class="[^"]*error[^"]*"[^>]*>(.*?)</span>',
            r'<div[^>]*class="[^"]*message[^"]*"[^>]*>(.*?)</div>',
        ]
        for pat in error_patterns:
            m = re.search(pat, html, re.DOTALL)
            if m:
                text = m.group(1) if m.lastindex else m.group(0)
                text = re.sub(r"<[^>]+>", " ", text).strip()
                if text and len(text) < 200:
                    return text
        return ""

    def submit_captcha_and_login(self, captcha_value: str = "") -> dict:
        """提交验证码并完成登录

        在 login() 返回 needs_captcha=True 后调用。
        填写验证码后重新尝试登录。

        参数:
            captcha_value: 验证码文本（仅对 image 类型有效）

        返回同 login()
        """
        try:
            self._ensure_browser()
            page = self.page

            # ── 1. 如果提供了验证码文本，填入 ──
            if captcha_value:
                captcha_input_selectors = [
                    "input[placeholder*='验证码']",
                    "input[placeholder*='验证']",
                    "input[id*='captcha']",
                    "input[id*='verify']",
                    "input[name*='captcha']",
                    "input[name*='verify']",
                    "input.ant-input[id*='captcha']",
                ]
                filled = False
                for sel in captcha_input_selectors:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.click()
                            _human_delay(0.2, 0.3)
                            el.fill("")
                            _human_delay(0.1, 0.2)
                            for char in captcha_value:
                                el.type(char, delay=random.randint(30, 80))
                            filled = True
                            break
                    except:
                        continue

                if not filled:
                    # 尝试找第三个或第四个 input（通常在用户名/密码之后）
                    inputs = page.query_selector_all(
                        "input:not([type='hidden']):not([type='password'])"
                    )
                    visible_inputs = [i for i in inputs if i.is_visible()]
                    if len(visible_inputs) >= 2:
                        captcha_field = visible_inputs[-1]  # 最后一个非密码输入框
                        captcha_field.click()
                        _human_delay(0.2, 0.3)
                        captcha_field.fill("")
                        for char in captcha_value:
                            captcha_field.type(char, delay=random.randint(30, 80))
                        filled = True

            _human_delay(0.5, 1.0)

            # ── 2. 点击登录按钮 ──
            login_btn = self._find_submit_button(page)
            if login_btn:
                login_btn.click()
            else:
                page.keyboard.press("Enter")

            _human_delay(2.0, 4.0)
            _human_delay(0.5, 1.0)

            # ── 3. 检查登录结果 ──
            if self._check_cookies_logged_in():
                return {
                    "success": True,
                    "logged_in": True,
                    "needs_captcha": False,
                    "cookies": self._get_cookie_string(),
                    "cookies_json": self._get_cookies_json(),
                    "error": "",
                    "message": "captcha_login_success",
                }

            # 检查是否又需要验证码
            captcha_again = self._detect_captcha()
            if captcha_again["has_captcha"]:
                return {
                    "success": True,
                    "logged_in": False,
                    "needs_captcha": True,
                    "image": captcha_again.get("image", ""),
                    "captcha_type": captcha_again["captcha_type"],
                    "error": "验证码错误或已过期，请重新填写",
                }

            # 提取错误信息
            page_content = page.content()
            error_msg = self._extract_error_message(page_content)
            if not error_msg:
                error_msg = "验证码登录失败"

            return {
                "success": False,
                "logged_in": False,
                "needs_captcha": False,
                "error": error_msg[:300],
                "image": self.take_screenshot(),
            }

        except Exception as e:
            return {"success": False, "logged_in": False,
                    "error": f"验证码处理异常: {e}"}

    def get_cookies(self) -> str:
        """获取当前浏览器的 cookie 字符串"""
        try:
            return self._get_cookie_string()
        except:
            return ""
