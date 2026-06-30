"""
Discuz! 签到插件 (k_misign)
继承 SigninBase，注册为 signin_discuz_k_misign
使用 platform_accounts 中已保存的 cookie 自动签到

扩展指南：
  新增论坛签到 → 在 plugins/ 下建 signin_xxx.py，
  继承 SigninBase + @register 即可，orchestrator 会自动发现
"""
import re, time, os, sys
from typing import Optional

# core/signin.py 由 orchestrator (forum_signin.py) 先行加载并注入 sys.modules
# 这里直接导入即可共享同一个 registry
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
from core_signin import SigninBase, register  # noqa: E402


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
        """检查该论坛是否安装 k_misign 签到插件"""
        if account.get("platform", "") != self.platform:
            return False
        cfg = account.get("config", {})
        site_url = cfg.get("site_url", "")
        if not site_url:
            return False
        try:
            import requests as _req
            test_url = site_url.rstrip("/") + "/k_misign-sign.html"
            check = _req.get(test_url, timeout=5, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            return check.status_code == 200 and "k_misign" in check.text.lower()
        except Exception:
            return False

    def signin(self) -> dict:
        """执行 k_misign 签到"""
        if not self.site_url or not self.cookie:
            return {"success": False, "already_signed": False,
                    "error": "缺少 site_url 或 cookie", "message": ""}

        try:
            from plugins.browser_session import HumanSession
        except ImportError:
            from browser_session import HumanSession

        browser = HumanSession(base_url=self.site_url, min_delay=0.5, max_delay=2.0)
        browser.set_cookies(self.cookie)

        sign_url = self.site_url.rstrip("/") + "/k_misign-sign.html"
        resp = browser.get(sign_url)

        uid_match = re.search(r"discuz_uid\s*=\s*'(\d+)'", resp.text)
        if not uid_match or uid_match.group(1) == "0":
            return {"success": False, "already_signed": False,
                    "error": "Cookie 无效，未登录", "message": ""}

        status_indicators = ["已签", "已签到", "签到成功", "今日已签", "您的签到排名"]
        if any(t in resp.text for t in status_indicators):
            return {"success": True, "already_signed": True,
                    "error": "", "message": "今天已签到"}

        formhash = None
        for pattern in [
            r'name="formhash"[^>]+value="([^"]+)"',
            r'formhash\s*=\s*"([^"]+)"',
            r'formhash=([a-zA-Z0-9]+)',
        ]:
            match = re.search(pattern, resp.text)
            if match:
                formhash = match.group(1)
                break

        if not formhash:
            link_match = re.search(
                r'k_misign:sign&operation=qiandao&formhash=([a-zA-Z0-9]+)',
                resp.text
            )
            if link_match:
                formhash = link_match.group(1)

        if not formhash:
            return {"success": False, "already_signed": False,
                    "error": "无法获取 formhash", "message": ""}

        qiandao_url = (
            f"{self.site_url}/plugin.php?id=k_misign:sign"
            f"&operation=qiandao&formhash={formhash}&format=empty"
        )
        sign_resp = browser.get(qiandao_url)

        time.sleep(1)
        verify_resp = browser.get(sign_url)
        if any(t in verify_resp.text for t in status_indicators):
            return {"success": True, "already_signed": False,
                    "error": "", "message": "签到成功 ✅"}

        if sign_resp.text.strip():
            msg = sign_resp.text.strip()[:200]
            if "今日已签" in msg or "签到成功" in msg or "succeed" in msg.lower():
                return {"success": True, "already_signed": False,
                        "error": "", "message": "签到成功 ✅"}
            return {"success": False, "already_signed": False,
                    "error": f"签到失败: {msg}", "message": ""}

        return {"success": False, "already_signed": False,
                "error": "签到失败，未知原因", "message": ""}
