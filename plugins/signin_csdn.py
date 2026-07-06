"""
CSDN 签到插件 — Playwright 方案

CSDN 签到在首页（https://www.csdn.net），页面上方有签到入口。
点击后弹出签到面板，可选择"签到"按钮完成每日签到。
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
        return account.get("platform", "") == self.platform

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
                    # 导航到 CSDN 首页
                    page.goto("https://www.csdn.net", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)

                    # 检查登录状态
                    if "passport.csdn.net" in page.url or "login" in page.url.lower():
                        return {"success": False, "already_signed": False,
                                "error": "Cookie 已过期", "message": ""}

                    body_text = page.inner_text("body")

                    # 检查是否已签到（CSDN 签到后通常会在页面显示签到状态或弹窗提示）
                    if "已签到" in body_text:
                        return {"success": True, "already_signed": True,
                                "error": "", "message": "今天已签到 ✅"}

                    # 尝试查找并点击签到入口
                    # CSDN 签到入口通常在顶部工具栏，文字为"签到"或"每日签到"
                    sign_btn = page.locator("text=签到").first

                    if sign_btn.count() > 0 and sign_btn.is_visible():
                        sign_btn.click()
                        page.wait_for_timeout(3000)

                        # 签到后可能会有弹窗或状态变化
                        after_body = page.inner_text("body")

                        if "已签到" in after_body or "签到成功" in after_body:
                            return {"success": True, "already_signed": False,
                                    "error": "", "message": "签到成功 ✅"}

                        # 检查是否弹出签到面板，里面可能有"签到"按钮
                        sign_panel_btn = page.locator("[class*='sign']:has-text('签到'), [class*='check']:has-text('签到')").first
                        if sign_panel_btn.count() > 0 and sign_panel_btn.is_visible():
                            sign_panel_btn.click()
                            page.wait_for_timeout(3000)
                            after_body2 = page.inner_text("body")
                            if "已签到" in after_body2 or "签到成功" in after_body2:
                                return {"success": True, "already_signed": False,
                                        "error": "", "message": "签到成功 ✅"}

                        return {"success": True, "already_signed": False,
                                "error": "", "message": "签到操作已完成"}
                    else:
                        return {"success": False, "already_signed": False,
                                "error": "找不到签到入口", "message": ""}

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
