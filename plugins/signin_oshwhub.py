"""
OSHWHub (立创开源硬件平台) 签到插件 — Playwright 方案

使用 Playwright 浏览器模拟签到，因为 OSHWHub 的 REST API 被 Cloudflare WAF 拦截。

签到页面: https://oshwhub.com/sign_in
按钮文字: "立即签到+1积分"
"""
import os, sys, json, logging, sqlite3
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
try:
    from core_signin import SigninBase, register
except ImportError:
    from core.signin import SigninBase, register

logger = logging.getLogger(__name__)


def _parse_cookies(cookie_str: str) -> list:
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        cookies.append({"name": n.strip(), "value": v.strip(), "domain": ".oshwhub.com", "path": "/"})
    return cookies


@register
class OshwhubSignin(SigninBase):
    name = "oshwhub_signin"
    display_name = "立创开源硬件平台 每日签到"
    platform = "oshwhub"
    config_fields = [
        {"key": "username", "label": "用户名/邮箱", "type": "text", "required": False, "default": ""},
        {"key": "password", "label": "密码", "type": "password", "required": False, "default": ""},
        {"key": "cookie", "label": "Cookie（备选）", "type": "password", "required": False,
         "placeholder": "登录后从浏览器 F12 复制"},
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        cfg = config or {}
        self.cookie = cfg.get("cookie", "")
        self.username = cfg.get("username", "")
        self.password = cfg.get("password", "")
        self.site_url = cfg.get("site_url", "https://oshwhub.com")

    def can_handle(self, account: dict) -> bool:
        if account.get("platform", "") != self.platform:
            return False
        cfg = account.get("config", {})
        # 只要有 cookie 或者有账号密码就能处理
        return bool(cfg.get("cookie", "")) or (bool(cfg.get("username", "")) and bool(cfg.get("password", "")))

    def _get_cookies(self):
        if not self.cookie:
            return []
        return _parse_cookies(self.cookie)

    def signin(self) -> dict:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True, args=[
                    '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                ])
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080}, locale="zh-CN",
                )

                # 优先用账号密码登录（获取新鲜 Cookie）
                if self.username and self.password and not self.cookie:
                    try:
                        from plugins.oshwhub_login import OshwhubPlaywrightLogin
                        login = OshwhubPlaywrightLogin(site_url=self.site_url)
                        result = login.login(self.username, self.password)
                        if result.get("logged_in") and result.get("cookies"):
                            self.cookie = result["cookies"]
                            # 保存 cookie 回原账号配置
                            _save_cookie_to_account_config(self.username, self.cookie)
                            # 使用 login 的 context
                            ctx = login.context
                            browser = login.browser
                        else:
                            login.close()
                            return {"success": False, "already_signed": False,
                                    "error": f"登录失败: {result.get('error', '未知错误')}", "message": ""}
                    except Exception as e:
                        return {"success": False, "already_signed": False,
                                "error": f"登录异常: {e}", "message": ""}

                # 如果有 cookie 但还没设置到 context
                if self.cookie and not ctx.cookies():
                    ctx.add_cookies(self._get_cookies())

                page = ctx.new_page()

                try:
                    # 导航到签到页
                    page.goto("https://oshwhub.com/sign_in", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)

                    # 检查是否已登录
                    if "login" in page.url.lower() or "passport" in page.url.lower():
                        # Cookie 过期了，尝试用账号密码重新登录
                        if self.username and self.password:
                            logger.info("Cookie 过期，尝试用账号密码重新登录...")
                            try:
                                from plugins.oshwhub_login import OshwhubPlaywrightLogin
                                login2 = OshwhubPlaywrightLogin(site_url=self.site_url)
                                result2 = login2.login(self.username, self.password)
                                if result2.get("logged_in") and result2.get("cookies"):
                                    self.cookie = result2["cookies"]
                                    _save_cookie_to_account_config(self.username, self.cookie)
                                    # 用新 context 替换
                                    ctx.close()
                                    ctx = login2.context
                                    browser = login2.browser
                                    page = ctx.new_page()
                                    page.goto("https://oshwhub.com/sign_in", wait_until="domcontentloaded", timeout=30000)
                                    page.wait_for_timeout(5000)
                                    logger.info("重新登录成功，继续签到流程")
                                else:
                                    login2.close()
                                    return {"success": False, "already_signed": False,
                                            "error": f"重新登录失败: {result2.get('error', '未知错误')}", "message": ""}
                            except Exception as e:
                                return {"success": False, "already_signed": False,
                                        "error": f"重新登录异常: {e}", "message": ""}
                        else:
                            return {"success": False, "already_signed": False,
                                    "error": "Cookie 已过期且无账号密码可重新登录", "message": ""}

                    # 检查是否已签到
                    body_text = page.inner_text("body")
                    if "已签到" in body_text or "今日已签" in body_text:
                        return {"success": True, "already_signed": True,
                                "error": "", "message": "今天已签到 ✅"}

                    # 点击"立即签到"
                    sign_btn = page.locator("text=立即签到").first

                    if sign_btn.count() > 0 and sign_btn.is_visible():
                        sign_btn.click()
                        page.wait_for_timeout(5000)

                        after_body = page.inner_text("body")
                        if "已签到" in after_body or "签到成功" in after_body:
                            return {"success": True, "already_signed": False,
                                    "error": "", "message": "签到成功 ✅ 获得积分"}
                        elif "+1积分" in after_body and "立即签到" not in after_body:
                            return {"success": True, "already_signed": False,
                                    "error": "", "message": "签到成功 ✅"}
                        else:
                            if "立即签到" not in page.inner_text("body"):
                                return {"success": True, "already_signed": False,
                                        "error": "", "message": "签到成功 ✅"}
                            return {"success": False, "already_signed": False,
                                    "error": "签到按钮点击后状态未改变", "message": ""}
                    else:
                        return {"success": False, "already_signed": False,
                                "error": "找不到签到按钮", "message": ""}

                except Exception as e:
                    return {"success": False, "already_signed": False,
                            "error": f"签到异常: {e}", "message": ""}
                finally:
                    page.close()
                    browser.close()

        except ImportError:
            return {"success": False, "already_signed": False,
                    "error": "Playwright 未安装", "message": ""}
        except Exception as e:
            return {"success": False, "already_signed": False,
                    "error": f"签到异常: {e}", "message": ""}


def _save_cookie_to_account_config(username_hint: str, cookie_str: str):
    """将签到获取的新鲜 Cookie 保存回数据库"""
    try:
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")
        )
        row = conn.execute(
            "SELECT id, config_json FROM platform_accounts WHERE platform='oshwhub' LIMIT 1"
        ).fetchone()
        if row and cookie_str:
            cfg = json.loads(row["config_json"]) if row["config_json"] else {}
            cfg["cookie"] = cookie_str
            conn.execute(
                "UPDATE platform_accounts SET config_json=? WHERE id=?",
                (json.dumps(cfg), row["id"]),
            )
            conn.commit()
            logger.info(f"✅ OSHWHub 签到: Cookie 已自动保存到 DB (账号: {username_hint})")
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ 保存 cookie 到 DB 失败: {e}")
