"""
CSDN 签到插件 — Playwright 方案

CSDN 签到入口在用户下拉菜单的"签到抽奖"链接，或直接访问:
https://i.csdn.net/#/user-center/draw

注意：
1. 必须严格使用 Playwright，禁止 requests/curl/wget。
2. CSDN 网页签到已迁移到微信小程序（"小程序签到"），
   /user-center/draw 页面仅显示抽奖中奖记录，无可用的网页签到按钮。
3. 插件会尝试查找签到入口，若找不到会报告清晰的状态。
"""
import os, sys, json, logging
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
        cookies.append({"name": n.strip(), "value": v.strip(), "domain": ".csdn.net", "path": "/"})
    return cookies


@register
class CsdnSignin(SigninBase):
    name = "csdn_signin"
    display_name = "CSDN 每日签到"
    platform = "csdn"
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录后从浏览器 F12 复制"},
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.cookie = (config or {}).get("cookie", "")

    def can_handle(self, account: dict) -> bool:
        return account.get("platform", "") == self.platform and bool(
            account.get("config", {}).get("cookie", ""))

    def _get_cookies(self):
        if not self.cookie:
            return []
        return _parse_cookies(self.cookie)

    def signin(self) -> dict:
        if not self.cookie:
            return {"success": False, "already_signed": False,
                    "error": "缺少 Cookie", "message": ""}

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
                ctx.add_cookies(self._get_cookies())
                page = ctx.new_page()

                try:
                    # 直接导航到签到抽奖页面
                    page.goto("https://i.csdn.net/#/user-center/draw",
                              wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)

                    # 检查是否已登录
                    if "passport.csdn.net" in page.url or "login" in page.url.lower():
                        return {"success": False, "already_signed": False,
                                "error": "Cookie 已过期", "message": ""}

                    body_text = page.inner_text("body")

                    # 检查是否已签到（签到页面会显示签到状态）
                    if "已签到" in body_text or "今日已签" in body_text or "签到成功" in body_text:
                        return {"success": True, "already_signed": True,
                                "error": "", "message": "今天已签到 ✅"}

                    # 找签到/抽奖按钮并点击
                    sign_btn = page.get_by_text("签到", exact=False).first

                    if sign_btn.count() > 0 and sign_btn.is_visible():
                        sign_btn.click(force=True)
                        page.wait_for_timeout(5000)

                        after_body = page.inner_text("body")
                        if "已签到" in after_body or "签到成功" in after_body or "今日已签" in after_body:
                            return {"success": True, "already_signed": False,
                                    "error": "", "message": "签到成功 ✅"}

                        return {"success": True, "already_signed": False,
                                "error": "", "message": "签到操作已完成"}
                    else:
                        # 检查是否显示的是抽奖记录页面（CSDN 网页签到已迁移到微信小程序）
                        if "小程序签到" in body_text or "抽奖记录" in body_text:
                            return {"success": False, "already_signed": False,
                                    "error": "CSDN 网页签到已迁移到微信小程序，暂不支持网页签到",
                                    "message": ""}
                        return {"success": False, "already_signed": False,
                                "error": "找不到签到按钮，页面可能已改版", "message": ""}

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
