"""
Discuz! 签到插件 (k_misign) — Playwright 版本
继承 SigninBase，注册为 signin_discuz_k_misign
使用 platform_accounts 中已保存的 cookie 自动签到

核心原则（死规矩）：
- 必须引用账号里的 cookie 凭证
- 必须用 Playwright（禁止 requests/curl/wget/httpx）

扩展指南：
  新增论坛签到 → 在 plugins/ 下建 signin_xxx.py，
  继承 SigninBase + @register 即可，orchestrator 会自动发现
"""
import re, time, os, sys
from typing import Optional

# core/signin.py 由 orchestrator (forum_signin.py) 先行加载并注入 sys.modules
# 这里直接导入即可共享同一个 registry
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
try:
    from core_signin import SigninBase, register  # noqa: E402
except ImportError:
    from flashsloth.core.signin import SigninBase, register


@register
class DiscuzKmisignSignin(SigninBase):
    name = "discuz_k_misign"
    display_name = "Discuz! 签到 (k_misign 插件)"
    platform = "discuz"
    config_fields = [
        {"key": "site_url", "label": "论坛地址", "type": "text", "required": True,
         "placeholder": "https://www.mydigit.cn"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录后复制 Cookie"},
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.site_url = (config or {}).get("site_url", "").rstrip("/")
        self.cookie = (config or {}).get("cookie", "")
        self.username = (config or {}).get("username", "")

    def can_handle(self, account: dict) -> bool:
        """检查是否可处理该论坛签到（要求有 site_url 和 cookie）"""
        if account.get("platform", "") != self.platform:
            return False
        cfg = account.get("config", {})
        site_url = cfg.get("site_url", "")
        if not site_url or not cfg.get("cookie", ""):
            return False
        # 有 site_url + cookie 就尝试签到
        return True

    def _parse_cookies(self, cookie_str: str) -> list:
        """将 Cookie 字符串解析为 Playwright 可接受的格式"""
        cookies = []
        domain = self.site_url.replace("https://", "").replace("http://", "").split("/")[0]
        # 确保 domain 以 "." 开头以便覆盖子域名
        main_domain = "." + domain if not domain.startswith(".") else domain
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            n, v = pair.split("=", 1)
            cookies.append({"name": n.strip(), "value": v.strip(),
                           "domain": main_domain, "path": "/"})
        return cookies

    def signin(self) -> dict:
        """使用 Playwright + BrowserEngine 执行 k_misign 签到"""
        if not self.site_url or not self.cookie:
            return {"success": False, "already_signed": False,
                    "error": "缺少 site_url 或 cookie", "message": ""}

        ctx = None
        try:
            from flashsloth.core.browser_engine import BrowserEngine
            from flashsloth.core.anti_detect import create_human_context, human_wait_page_ready

            # 复用常驻浏览器引擎
            engine = BrowserEngine.get_instance()
            if not engine.is_ready():
                engine.start()
            browser = engine.get_browser()
            if not browser:
                raise RuntimeError("BrowserEngine 未就绪")

            # 在共享浏览器上创建隔离上下文（Cookie/会话隔离）
            ctx = create_human_context(browser)

            # 注入 Cookie
            cookies = self._parse_cookies(self.cookie)
            if cookies:
                ctx.add_cookies(cookies)

            page = ctx.new_page()

            sign_url = self.site_url.rstrip("/") + "/k_misign-sign.html"
            page.goto(sign_url, wait_until="domcontentloaded", timeout=30000)
            human_wait_page_ready(page, min_sec=2.0)

            # 检查是否登录
            html = page.content()
            uid_match = re.search(r'discuz_uid\s*=\s*["\'](\d+)["\']', html)
            if not uid_match or uid_match.group(1) == "0":
                ctx.close()
                return {"success": False, "already_signed": False,
                        "error": "Cookie 无效，未登录", "message": ""}

            # 检查是否已签到
            status_indicators = ["已签", "已签到", "签到成功", "今日已签", "您的签到排名"]
            if any(t in html for t in status_indicators):
                ctx.close()
                return {"success": True, "already_signed": True,
                        "error": "", "message": "今天已签到"}

            # 提取 formhash
            formhash = None
            for pattern in [
                r'name="formhash"[^>]+value="([^"]+)"',
                r'formhash\s*=\s*"([^"]+)"',
                r'formhash=([a-zA-Z0-9]+)',
            ]:
                match = re.search(pattern, html)
                if match:
                    formhash = match.group(1)
                    break

            if not formhash:
                link_match = re.search(
                    r'k_misign:sign&operation=qiandao&formhash=([a-zA-Z0-9]+)',
                    html
                )
                if link_match:
                    formhash = link_match.group(1)

            if not formhash:
                ctx.close()
                return {"success": False, "already_signed": False,
                        "error": "无法获取 formhash", "message": ""}

            # 执行签到 — 直接访问签到链接
            qiandao_url = (
                f"{self.site_url}/plugin.php?id=k_misign:sign"
                f"&operation=qiandao&formhash={formhash}&format=empty"
            )
            page.goto(qiandao_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # 验证签到结果
            page.goto(sign_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)
            verify_html = page.content()

            if any(t in verify_html for t in status_indicators):
                ctx.close()
                return {"success": True, "already_signed": False,
                        "error": "", "message": "签到成功 ✅"}

            # 检查响应内容
            body_text = page.inner_text("body")
            if body_text:
                if "今日已签" in body_text or "签到成功" in body_text or "succeed" in body_text.lower():
                    ctx.close()
                    return {"success": True, "already_signed": False,
                            "error": "", "message": "签到成功 ✅"}
                ctx.close()
                return {"success": False, "already_signed": False,
                        "error": f"签到失败: {body_text[:200]}", "message": ""}

            ctx.close()
            return {"success": False, "already_signed": False,
                    "error": "签到失败，未知原因", "message": ""}

        except Exception as e:
            # 确保隔离上下文在异常时也关闭
            if ctx:
                try:
                    ctx.close()
                except Exception:
                    pass
            return {"success": False, "already_signed": False,
                    "error": f"签到异常: {e}", "message": ""}
