"""
OSHWHub (立创开源硬件平台) 签到插件 — Playwright 浏览器方案

由于 OSHWHub 有 WAF 反爬保护（HTTP 418），
只能通过 Playwright 模拟真实浏览器进行签到。

签到流程：
1. 用 Playwright 打开 /sign_in 页面
2. 检查是否已签到（页面文本检测）
3. 若未签到，点击签到按钮
4. 等待签到结果
"""

import json, re, os, sys, base64, random, time
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
from core_signin import SigninBase, register


def _find_chromium() -> str:
    """查找可用的 Chromium 浏览器路径（复用 oshwhub_login 的查找逻辑）"""
    candidates = [
        os.path.expanduser("~/.hermes/playwright-browsers/chromium-1228/chrome-linux64/chrome"),
        "/tmp/chrome-extracted/chrome-linux64/chrome",
        "/opt/hermes/.playwright/chromium-1228/chrome",
    ]
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
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


@register
class OshwhubSignin(SigninBase):
    name = "oshwhub_signin"
    display_name = "立创开源硬件平台 每日签到"
    platform = "oshwhub"
    config_fields = [
        {"key": "site_url", "label": "平台地址", "type": "text", "required": True,
         "default": "https://oshwhub.com", "placeholder": "https://oshwhub.com"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录后从浏览器 F12 复制"},
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.site_url = (config or {}).get("site_url", "https://oshwhub.com").rstrip("/")
        self.cookie = (config or {}).get("cookie", "")
        self.username = (config or {}).get("username", "")

    def can_handle(self, account: dict) -> bool:
        """判断此插件是否能处理该账号"""
        if account.get("platform", "") != self.platform:
            return False
        cfg = account.get("config", {})
        cookie = cfg.get("cookie", "")
        return bool(cookie)

    def signin(self) -> dict:
        """使用 Playwright 浏览器签到"""
        if not self.cookie:
            return {"success": False, "already_signed": False,
                    "error": "缺少 Cookie", "message": ""}

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"success": False, "already_signed": False,
                    "error": "缺少 Playwright，请安装: pip install playwright", "message": ""}

        browser = None
        context = None
        page = None
        pw = None

        try:
            pw = sync_playwright().start()
            chrome_path = _find_chromium()
            if chrome_path:
                browser = pw.chromium.launch(
                    headless=True,
                    executable_path=chrome_path,
                    args=["--no-sandbox", "--disable-setuid-sandbox",
                          "--disable-dev-shm-usage", "--disable-gpu"],
                )
            else:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox",
                          "--disable-dev-shm-usage", "--disable-gpu"],
                )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
            )

            # 注入 Cookie
            if self.cookie:
                domain = self.site_url.replace("https://", "").replace("http://", "").split("/")[0]
                for item in self.cookie.split(";"):
                    item = item.strip()
                    if "=" in item:
                        name, value = item.split("=", 1)
                        try:
                            context.add_cookies([{
                                "name": name.strip(),
                                "value": value.strip(),
                                "domain": domain,
                                "path": "/",
                            }])
                        except:
                            pass

            page = context.new_page()

            # ── 访问签到页面 ──
            sign_url = f"{self.site_url}/sign_in"
            page.goto(sign_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)  # 等待 JS 渲染

            page_text = page.inner_text("body")

            # ── 检查是否已签到 ──
            already_indicators = ["已签到", "签到成功", "todaySigned", "already signed"]
            if any(ind in page_text for ind in already_indicators):
                return {"success": True, "already_signed": True,
                        "error": "", "message": "今天已签到 ✅"}

            # ── 查找签到按钮并点击 ──
            sign_btn = None
            btn_selectors = [
                "button:has-text('签到')",
                "button:has-text('打卡')",
                ".sign-btn",
                "[class*='sign'] button",
                "button[class*='sign']",
                "div[class*='sign'] button",
                "button:has-text('每日签到')",
            ]

            for sel in btn_selectors:
                try:
                    els = page.query_selector_all(sel)
                    for el in els:
                        if el.is_visible():
                            sign_btn = el
                            break
                except:
                    continue
                if sign_btn:
                    break

            if not sign_btn:
                # 尝试通过文本查找
                try:
                    sign_btn = page.get_by_text("签到", exact=False).first
                    if sign_btn and sign_btn.is_visible():
                        pass
                    else:
                        sign_btn = None
                except:
                    pass

            if sign_btn:
                sign_btn.click()
                time.sleep(2)

                # 等待签到结果
                new_text = page.inner_text("body")
                if any(ind in new_text for ind in already_indicators):
                    return {"success": True, "already_signed": False,
                            "error": "", "message": "签到成功 ✅"}

                # 检查是否有签到结果提示
                try:
                    result_text = page.inner_text("body")
                    if "签到成功" in result_text or "获得" in result_text:
                        return {"success": True, "already_signed": False,
                                "error": "", "message": "签到成功 ✅"}
                except:
                    pass

                return {"success": True, "already_signed": False,
                        "error": "", "message": "签到按钮已点击，请到 OSHWHub 确认结果"}

            return {"success": False, "already_signed": False,
                    "error": "未找到签到按钮（网站可能改版或 Cookie 无效）",
                    "message": ""}

        except Exception as e:
            return {"success": False, "already_signed": False,
                    "error": f"签到异常: {e}", "message": ""}
        finally:
            try:
                if context: context.close()
            except:
                pass
            try:
                if browser: browser.close()
            except:
                pass
            try:
                if pw: pw.stop()
            except:
                pass
