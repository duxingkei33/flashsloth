"""
闲鱼 (Xianyu) Publisher — 通过 Playwright 登录 + Cookie 方式操作闲鱼

支持两种登录方式：
  1. Cookie 方式：用户通过 Playwright 浏览器自动登录后保存 Cookie
  2. Playwright 浏览器自动登录：填写淘宝账号密码，处理验证码/扫码

登录流程：
  1. 打开 goofish.com → 点击登录 → 跳转淘宝 SSO
  2. 填入淘宝账号密码 → 检测验证码类型
  3. 截图返回 → 用户处理验证码/扫码 → 确认登录
  4. 登录成功 → 保存 Cookie

注意：
  - 淘宝登录有强反爬机制，大概率需要手机扫码
  - 单账号不超过 3次/分钟登录
  - 实际发布商品需对接闲鱼开放平台 API，目前以登录 + Cookie 管理为主
"""
import re, json, time, random
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError

try:
    from flashsloth.plugins.xianyu_login import XianyuPlaywrightLogin
except ImportError:
    from plugins.xianyu_login import XianyuPlaywrightLogin


@register
class XianyuPublisher(Publisher):
    name = "xianyu"
    display_name = "闲鱼"
    config_fields = [
        {
            "key": "login_mode",
            "label": "登录方式",
            "type": "select",
            "required": True,
            "options": [
                {"value": "cookie", "label": "Cookie 直接访问"},
                {"value": "playwright", "label": "浏览器自动登录（需淘宝账号密码）"},
            ],
            "placeholder": "选择登录方式",
        },
        {
            "key": "taobao_account",
            "label": "淘宝账号",
            "type": "text",
            "required": False,
            "placeholder": "登录闲鱼的淘宝账号（手机号/邮箱）",
        },
        {
            "key": "password",
            "label": "淘宝密码",
            "type": "password",
            "required": False,
            "placeholder": "淘宝登录密码",
        },
        {
            "key": "cookie",
            "label": "Cookie（Cookie模式）",
            "type": "password",
            "required": False,
            "placeholder": "登录后从浏览器 F12 复制 Cookie",
        },
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.login_mode = config.get("login_mode", "cookie")
        self.taobao_account = config.get("taobao_account", "")
        self.password = config.get("password", "")
        self._login_instance: XianyuPlaywrightLogin | None = None

    def validate_config(self) -> list[str]:
        missing = []
        if self.login_mode == "cookie" and not self.config.get("cookie", ""):
            missing.append("Cookie")
        if self.login_mode == "playwright":
            if not self.taobao_account:
                missing.append("淘宝账号")
            if not self.password:
                missing.append("密码")
        return missing

    def test_connection(self) -> dict:
        """测试连接 — 根据登录方式检查"""
        if self.login_mode == "cookie":
            return self._test_cookie()
        return {
            "success": False,
            "error": "Playwright 模式需先验证验证码才能测试连接",
            "needs_captcha": True,
        }

    def _test_cookie(self) -> dict:
        """测试 Cookie — 模拟访问 goofish.com"""
        cookie = self.config.get("cookie", "")
        if not cookie:
            return {
                "success": False,
                "error": "Cookie 为空，请先登录获取",
                "status": "无 Cookie",
            }
        try:
            import requests
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Cookie": cookie,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            resp = requests.get(
                "https://goofish.com", headers=headers, timeout=10,
                allow_redirects=True,
            )
            text = resp.text.lower()
            if resp.status_code == 200:
                user_keywords = ["my", "user", "个人", "我的", "logout", "退出"]
                if any(kw in text for kw in user_keywords):
                    return {"success": True, "error": "", "status": "已登录"}
                return {
                    "success": True, "error": "",
                    "status": "Cookie 有效，但无法确认登录状态（可能需后续验证）",
                }
            if "login" in resp.url.lower():
                return {
                    "success": False,
                    "error": "Cookie 已过期，请重新登录获取",
                    "status": "Cookie 过期",
                }
            return {
                "success": False,
                "error": f"请求异常 (状态码: {resp.status_code})",
                "status": "连接失败",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"连接失败: {e}",
                "status": "连接失败",
            }

    # ─── Playwright 浏览器登录 ──────────────────────

    def playwright_login(self) -> dict:
        """使用 Playwright 浏览器自动登录闲鱼

        返回:
            success: bool
            logged_in: bool     — 是否最终登录成功
            needs_captcha: bool — 是否需要验证码/扫码
            image: str          — 截图（base64）
            captcha_type: str   — "qr_scan" | "slider" | "sms" | "none"
            cookies: str        — 登录成功时的 cookie
            error: str
            message: str
        """
        if not self.taobao_account or not self.password:
            return {
                "success": False, "logged_in": False,
                "error": "请先在配置中填写淘宝账号和密码",
            }

        try:
            login = XianyuPlaywrightLogin()
            self._login_instance = login
            result = login.login(
                taobao_account=self.taobao_account,
                password=self.password,
            )

            if result.get("logged_in"):
                cookie_str = result.get("cookies", "")
                self.config["cookie"] = cookie_str

            return result

        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"Playwright 登录异常: {e}",
            }

    def check_playwright_login_status(self) -> dict:
        """检查 Playwright 登录状态（用户处理验证码/扫码后调用）

        返回同 playwright_login()
        """
        try:
            login = self._login_instance or XianyuPlaywrightLogin()
            self._login_instance = login
            result = login.check_login_status()

            if result.get("logged_in"):
                cookie_str = result.get("cookies", "")
                self.config["cookie"] = cookie_str

            return result

        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"检查登录状态异常: {e}",
            }

    def close_browser(self):
        """关闭 Playwright 浏览器"""
        if self._login_instance:
            try:
                self._login_instance.close()
            except Exception:
                pass
            self._login_instance = None

    def get_cookies(self) -> str:
        """获取当前保存的 cookie"""
        return self.config.get("cookie", "")

    # ─── 发布商品 ──────────────────────────────────

    def publish(self, article: Article, **kwargs) -> dict:
        """发布商品到闲鱼（框架预留）

        当前仅支持 Cookie 验证和管理。
        实际发布商品需要：
          1. 有效的闲鱼/淘宝认证 Cookie
          2. 闲鱼开放平台 API 或浏览器自动化发布

        返回: {"success": bool, "url": str, "id": str, "error": str}
        """
        missing = self.validate_config()
        if missing:
            return {
                "success": False, "url": "", "id": "",
                "error": f"缺少配置: {', '.join(missing)}",
            }

        if self.login_mode == "playwright":
            return {
                "success": False, "url": "", "id": "",
                "error": "请先完成浏览器登录后再发布商品",
            }

        if not self._has_valid_cookie():
            return {
                "success": False, "url": "", "id": "",
                "error": "Cookie 无效或已过期，请重新登录获取",
            }

        return {
            "success": False, "url": "", "id": "",
            "error": "闲鱼发布功能需要对接开放平台 API，当前版本尚未实现",
        }

    def _has_valid_cookie(self) -> bool:
        """检查 Cookie 中是否包含关键认证字段"""
        cookie = self.config.get("cookie", "")
        if not cookie:
            return False
        required = ["_tb_token_", "cookie2", "t", "sid", "alimamapwg"]
        return sum(1 for k in required if k in cookie) >= 2

    def __del__(self):
        self.close_browser()
