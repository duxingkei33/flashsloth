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
    from flashsloth.core.signin import SigninBase, register

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
        # 解密敏感字段（DB 中可能加密存储）
        try:
            from flashsloth.core.credential_crypto import decrypt_config
            decrypt_config(cfg)
        except ImportError:
            try:
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
                from core.credential_crypto import decrypt_config
                decrypt_config(cfg)
            except ImportError:
                pass
            except Exception:
                pass
        except Exception:
            pass
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
        """在独立线程中运行 Playwright，避免 asyncio 冲突"""
        import threading
        result_holder = {}
        exception_holder = []

        def _run():
            try:
                result_holder["data"] = self._sync_signin_impl()
            except Exception as e:
                exception_holder.append(e)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=180)
        if exception_holder:
            return {"success": False, "already_signed": False,
                    "error": f"签到线程异常: {exception_holder[0]}", "message": ""}
        return result_holder.get("data", {"success": False, "already_signed": False,
                                          "error": "签到线程无返回值", "message": ""})

    def _sync_signin_impl(self) -> dict:
        """同步 Playwright 签到的实际实现"""
        from playwright.sync_api import sync_playwright

        try:
            # 方案 A: 有 Cookie 尝试签到
            if self.cookie:
                result = self._do_signin_with_cookie(sync_playwright)
                # Cookie 签到成功或已签到 → 返回
                if result.get("success") or result.get("already_signed"):
                    return result
                # Cookie 过期且有密码 → fallback 到密码登录
                if self.password and self.username:
                    logger.info("Cookie 过期，尝试密码登录重新获取 Cookie")
                    return self._login_and_signin()
                # Cookie 过期且无密码 → 报告错误
                return result

            # 方案 B: 无 Cookie，直接用密码登录签到
            if self.password and self.username:
                return self._login_and_signin()

            return {"success": False, "already_signed": False,
                    "error": "无可用凭证（无 Cookie 也无密码）", "message": ""}

        except Exception as e:
            return {"success": False, "already_signed": False,
                    "error": f"签到异常: {e}", "message": ""}

    def _login_and_signin(self) -> dict:
        """用密码登录 OSHWHub 并签到"""
        from plugins.oshwhub_login import OshwhubPlaywrightLogin
        login = OshwhubPlaywrightLogin(site_url=self.site_url)
        result = login.login(self.username, self.password)
        if not (result.get("logged_in") and result.get("cookies")):
            login.close()
            return {"success": False, "already_signed": False,
                    "error": f"登录失败: {result.get('error', '未知错误')}", "message": ""}

        self.cookie = result["cookies"]
        _save_cookie_to_account_config(self.username, self.cookie)

        # 复用 login 的上下文签到
        return self._do_signin_with_context(
            browser=login.browser, ctx=login.context
        )

    def _do_signin_with_cookie(self, _pw_fn) -> dict:
        """用 Cookie 签到（独立 Playwright 实例）"""
        with _pw_fn() as pw:
            browser = pw.chromium.launch(headless=True, args=[
                '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
            ])
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080}, locale="zh-CN",
            )
            try:
                ctx.add_cookies(self._get_cookies())
            except:
                pass
            page = ctx.new_page()
            return self._check_signin_page(page, browser, ctx)

    def _do_signin_with_context(self, browser, ctx) -> dict:
        """用已有的浏览器上下文签到（无独立的 PW 实例）"""
        page = ctx.new_page()
        return self._check_signin_page(page, browser, ctx)

    def _check_signin_page(self, page, browser, ctx):
        """导航到签到页并执行签到"""
        try:
            # 导航到签到页
            page.goto("https://oshwhub.com/sign_in", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            # 检查是否已登录
            if "login" in page.url.lower() or "passport" in page.url.lower():
                # Cookie 过期
                return {"success": False, "already_signed": False,
                        "error": "Cookie 已过期且无可用凭证重新登录", "message": ""}

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
            try:
                page.close()
                browser.close()
            except:
                pass


def _save_cookie_to_account_config(username_hint: str, cookie_str: str):
    """将签到获取的新鲜 Cookie 保存回数据库（加密存储）"""
    try:
        from flashsloth.core.credential_crypto import decrypt_config, encrypt_config
        
        conn = sqlite3.connect(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")
        )
        row = conn.execute(
            "SELECT id, config_json FROM platform_accounts WHERE platform='oshwhub' LIMIT 1"
        ).fetchone()
        if row and cookie_str:
            cfg = json.loads(row[1]) if row[1] else {}
            decrypt_config(cfg)  # 先解密
            cfg["cookie"] = cookie_str
            encrypt_config(cfg)  # 重新加密
            conn.execute(
                "UPDATE platform_accounts SET config_json=? WHERE id=?",
                (json.dumps(cfg), row[0]),
            )
            conn.commit()
            logger.info(f"✅ OSHWHub 签到: Cookie 已自动保存到 DB (账号: {username_hint})")
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ 保存 cookie 到 DB 失败: {e}")
