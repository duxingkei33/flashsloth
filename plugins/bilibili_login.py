"""Bilibili (哔哩哔哩) Playwright 登录器 — 浏览器自动化登录

Bilibili 登录页在 passport.bilibili.com，支持多种登录方式：
1. QR 码扫码登录（推荐 — 无需验证码）
2. 密码登录（极验 Geetest 滑块验证码）
3. 第三方登录（QQ/微博/微信 OAuth）

Publisher (`publisher_bilibili.py`) 使用 API 方式发布文章，不需要 Playwright。
此登录器仅用于首次获取 Cookie（QR 码截图/密码登录/验证码处理）。

Bilibili 认证所需 Cookie：
- SESSDATA（会话令牌）
- bili_jct（CSRF 保护）
- DedeUserID（用户 ID）

参考文档：
- passport 登录: https://passport.bilibili.com/login
- QR 码 API: /x/passport-login/web/qrcode/generate（生成）/poll（轮询）
- 登录状态检测: https://api.bilibili.com/x/web-interface/nav
"""
import os, re, time, json, base64, random
from typing import Optional


def _human_delay(min_s: float = 0.5, max_s: float = 2.0):
    """人机延迟模拟"""
    time.sleep(random.uniform(min_s, max_s))


class BilibiliPlaywrightLogin:
    """Bilibili Playwright 登录器

    支持 QR 码扫码登录（推荐）和密码登录（需处理极验 Geetest 验证码）。

    用法:
        login = BilibiliPlaywrightLogin()
        result = login.login()
        if result["logged_in"]:
            cookies = result["cookies"]
    """

    LOGIN_URL = "https://passport.bilibili.com/login"
    BAPI = "https://api.bilibili.com"

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._screenshot = None
        self._pw = None

    def __del__(self):
        self.close()

    def close(self):
        """释放浏览器资源"""
        try:
            if self.page:
                self.page.close()
        except Exception:
            pass
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self.page = None
        self.context = None
        self.browser = None
        self._pw = None

    def _ensure_browser(self):
        """确保浏览器已启动并注入反检测脚本"""
        if self.browser and self.page:
            try:
                self.page.title()
                return
            except Exception:
                self.close()

        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        self.context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )
        # 注入反自动化检测脚本
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
        """)
        self.page = self.context.new_page()

    def _get_condensed_cookies(self) -> str:
        """从 Playwright context 提取关键 Cookie 为字符串"""
        try:
            all_cookies = self.context.cookies()
            # 只保留 bilibili.com 域的必要 Cookie
            bili_cookies = []
            for c in all_cookies:
                if "bilibili.com" in c.get("domain", "") or "passport.bilibili.com" in c.get("domain", ""):
                    bili_cookies.append(c)

            # 构建 Cookie 字符串，确保包含关键字段
            parts = {}
            for c in bili_cookies:
                parts[c["name"]] = c["value"]

            # 如果已经有了 SESSDATA + bili_jct，可能已登录成功
            cookie_str = "; ".join(f"{k}={v}" for k, v in parts.items())
            return cookie_str
        except Exception:
            return ""

    def _check_login_success(self) -> bool:
        """通过 API 检测是否已登录"""
        cookie_str = self._get_condensed_cookies()
        if not cookie_str:
            return False
        # 检查关键字段
        has_sessdata = "SESSDATA" in cookie_str
        has_bili_jct = "bili_jct" in cookie_str
        if not (has_sessdata and has_bili_jct):
            return False

        # 通过 API 确认登录状态
        try:
            import requests as req

            resp = req.get(
                f"{self.BAPI}/x/web-interface/nav",
                headers={
                    "Cookie": cookie_str,
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.bilibili.com/",
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
                return True
        except Exception:
            pass
        return False

    def login_qrcode(self, max_wait: int = 120) -> dict:
        """QR 码扫码登录

        流程：
        1. 打开 passport 登录页 → 切换到 QR 码 Tab
        2. 截图返回（显示二维码）
        3. 轮询检测登录状态

        Args:
            max_wait: 最长等待秒数（默认 120s）

        Returns:
            {"logged_in": bool, "cookies": str, "username": str, "screenshot": base64, "error": str}
        """
        self._ensure_browser()
        result = {"logged_in": False, "cookies": "", "username": "", "screenshot": "", "error": ""}

        try:
            # 打开登录页
            self.page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)

            # 切换到 OR 码登录 Tab（Bilibili 登录页有 Tab 切换）
            # 选择「扫码登录」标签
            try:
                qrcode_tab = self.page.query_selector(".login-tabs .tab-item:has-text('扫码登录')")
                if qrcode_tab:
                    qrcode_tab.click()
                    _human_delay(1, 2)
            except Exception:
                pass

            # 等待二维码渲染
            self.page.wait_for_timeout(2000)

            # 截图（二维码）
            self._screenshot = self.page.screenshot(type="png")
            result["screenshot"] = base64.b64encode(self._screenshot).decode("utf-8")

            # 轮询登录状态
            poll_interval = 3  # 每 3 秒检查一次
            elapsed = 0
            while elapsed < max_wait:
                if self._check_login_success():
                    cookie_str = self._get_condensed_cookies()
                    result["logged_in"] = True
                    result["cookies"] = cookie_str

                    # 获取用户名
                    try:
                        import requests as req

                        resp = req.get(
                            f"{self.BAPI}/x/web-interface/nav",
                            headers={"Cookie": cookie_str, "User-Agent": "..."},
                            timeout=10,
                        )
                        data = resp.json()
                        if data.get("code") == 0:
                            result["username"] = data.get("data", {}).get("uname", "")
                    except Exception:
                        pass
                    return result

                time.sleep(poll_interval)
                elapsed += poll_interval

            result["error"] = f"QR 码登录超时（等待 {max_wait}s）"

        except Exception as e:
            result["error"] = f"QR 登录异常: {e}"

        return result

    def login_password(self, username: str, password: str) -> dict:
        """密码登录（可能触发极验 Geetest 验证码）

        Args:
            username: 用户名/邮箱
            password: 密码

        Returns:
            {"logged_in": bool, "cookies": str, "username": str,
             "needs_captcha": bool, "screenshot": str, "error": str}
        """
        self._ensure_browser()
        result = {
            "logged_in": False, "cookies": "", "username": "",
            "needs_captcha": False, "captcha_type": "", "screenshot": "", "error": "",
        }

        try:
            # 打开登录页
            self.page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)

            # 切换到「密码登录」Tab
            try:
                password_tab = self.page.query_selector(".login-tabs .tab-item:has-text('密码登录')")
                if password_tab:
                    password_tab.click()
                    _human_delay(1, 2)
            except Exception:
                pass

            # 填写账号
            try:
                username_input = self.page.query_selector("input[placeholder='请输入账号']")
                if username_input:
                    username_input.click()
                    _human_delay(0.3, 0.8)
                    username_input.fill(username)
                    _human_delay(0.5, 1.0)
            except Exception:
                pass

            # 填写密码
            try:
                password_input = self.page.query_selector("input[placeholder='请输入密码']")
                if password_input:
                    password_input.click()
                    _human_delay(0.3, 0.8)
                    password_input.fill(password)
                    _human_delay(0.5, 1.0)
            except Exception:
                pass

            # 检查是否有极验 Geetest 验证码
            geetest = self.page.query_selector(".geetest_holder, .geetest_panel, .geetest_radar_tip")
            if geetest or "geetest" in (self.page.content()[:5000]).lower():
                result["needs_captcha"] = True
                result["captcha_type"] = "geetest_slider"
                self._screenshot = self.page.screenshot(type="png")
                result["screenshot"] = base64.b64encode(self._screenshot).decode("utf-8")
                result["error"] = "需要处理极验(GeeTest)滑块验证码"
                return result

            # 点击登录按钮
            try:
                login_btn = self.page.query_selector("button:has-text('登录')")
                if login_btn:
                    login_btn.click()
                    _human_delay(2, 4)
            except Exception:
                pass

            # 等待登录结果（最多 15 秒）
            for _ in range(15):
                if self._check_login_success():
                    cookie_str = self._get_condensed_cookies()
                    result["logged_in"] = True
                    result["cookies"] = cookie_str

                    # 获取用户名
                    try:
                        import requests as req

                        resp = req.get(
                            f"{self.BAPI}/x/web-interface/nav",
                            headers={"Cookie": cookie_str, "User-Agent": "..."},
                            timeout=10,
                        )
                        data = resp.json()
                        if data.get("code") == 0:
                            result["username"] = data.get("data", {}).get("uname", "")
                    except Exception:
                        pass
                    return result

                # 检查是否触发了验证码
                if not result["needs_captcha"]:
                    geetest = self.page.query_selector(
                        ".geetest_holder, .geetest_panel, .geetest_radar_tip"
                    )
                    if geetest or "geetest" in (self.page.content()[:3000]).lower():
                        result["needs_captcha"] = True
                        result["captcha_type"] = "geetest_slider"
                        self._screenshot = self.page.screenshot(type="png")
                        result["screenshot"] = base64.b64encode(self._screenshot).decode("utf-8")
                        result["error"] = "登录触发极验验证码，需要手动处理"
                        return result

                time.sleep(1)

            result["error"] = "登录超时，请检查账号密码"

        except Exception as e:
            result["error"] = f"密码登录异常: {e}"

        return result

    def login(self, username: str = "", password: str = "", mode: str = "qrcode") -> dict:
        """统一登录入口

        默认使用 QR 码登录（推荐，无需验证码）。
        提供了账号密码也可用 password 模式。

        Args:
            username: B站用户名/邮箱（password 模式需要）
            password: B站密码（password 模式需要）
            mode: "qrcode"（推荐）或 "password"

        Returns:
            {"logged_in": bool, "cookies": str, ...}
        """
        if mode == "qrcode" or (mode == "auto" and not (username and password)):
            return self.login_qrcode()
        elif mode == "password" or (mode == "auto" and username and password):
            return self.login_password(username, password)
        return {"logged_in": False, "cookies": "", "error": f"未知登录模式: {mode}"}

    def take_screenshot(self) -> str:
        """获取当前页面的 base64 截图"""
        if not self.page:
            return ""
        try:
            png = self.page.screenshot(type="png")
            return base64.b64encode(png).decode("utf-8")
        except Exception:
            return ""
