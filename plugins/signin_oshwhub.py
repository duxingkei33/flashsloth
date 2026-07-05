"""
OSHWHub (立创开源硬件平台) 签到插件 — REST API 方案

使用 OSHWHub 的内部 REST API 进行签到，无需 Playwright 浏览器。

API 端点:
  GET  /api/users/getSignInProfile  → 查询签到状态
  POST /api/users/signIn            → 执行签到
"""
import json, os, sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
try:
    from core_signin import SigninBase, register
except ImportError:
    from core.signin import SigninBase, register


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
        self._session = None

    def can_handle(self, account: dict) -> bool:
        if account.get("platform", "") != self.platform:
            return False
        cfg = account.get("config", {})
        return bool(cfg.get("cookie", ""))

    def _get_session(self):
        """获取带 Cookie 的 requests Session"""
        if self._session:
            return self._session
        import requests
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": self.site_url,
            "Referer": f"{self.site_url}/sign_in",
            "X-Requested-With": "XMLHttpRequest",
        })
        domain = self.site_url.replace("https://", "").replace("http://", "").split("/")[0]
        if self.cookie:
            for item in self.cookie.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    self._session.cookies.set(k.strip(), v.strip(), domain=domain)
        return self._session

    def signin(self) -> dict:
        """使用 REST API 直接签到"""
        if not self.cookie:
            return {"success": False, "already_signed": False,
                    "error": "缺少 Cookie", "message": ""}

        session = self._get_session()

        try:
            # 第一步：检查签到状态
            profile_resp = session.get(
                f"{self.site_url}/api/users/getSignInProfile",
                timeout=15,
            )
            if profile_resp.status_code != 200:
                return {"success": False, "already_signed": False,
                        "error": f"获取签到状态失败 (HTTP {profile_resp.status_code})",
                        "message": ""}

            profile_data = profile_resp.json()
            if not profile_data.get("success"):
                return {"success": False, "already_signed": False,
                        "error": f"API 返回错误: {profile_data.get('message', '未知')}",
                        "message": ""}

            is_today_signed = profile_data.get("result", {}).get("isTodaySignIn", False)
            if is_today_signed:
                return {"success": True, "already_signed": True,
                        "error": "", "message": "今天已签到 ✅"}

            # 第二步：执行签到
            sign_resp = session.post(
                f"{self.site_url}/api/users/signIn",
                json={},
                timeout=15,
            )

            if sign_resp.status_code != 200:
                return {"success": False, "already_signed": False,
                        "error": f"签到 API 返回 HTTP {sign_resp.status_code}",
                        "message": ""}

            sign_data = sign_resp.json()
            if sign_data.get("success"):
                # result 为 true 表示签到成功，false 可能表示重复签到
                if sign_data.get("result") == True:
                    return {"success": True, "already_signed": False,
                            "error": "", "message": "签到成功 ✅ 获得积分"}
                elif sign_data.get("result") == False:
                    # 可能已经签过了或者签到失败
                    # 再查一次确认
                    check_resp = session.get(
                        f"{self.site_url}/api/users/getSignInProfile",
                        timeout=15,
                    )
                    if check_resp.status_code == 200:
                        check_data = check_resp.json()
                        if check_data.get("result", {}).get("isTodaySignIn"):
                            return {"success": True, "already_signed": True,
                                    "error": "", "message": "今天已签到 ✅"}
                    return {"success": False, "already_signed": False,
                            "error": "签到返回 false，可能重复签到或签到失败",
                            "message": ""}
            else:
                return {"success": False, "already_signed": False,
                        "error": f"签到失败: {sign_data.get('message', '未知错误')}",
                        "message": ""}

        except Exception as e:
            return {"success": False, "already_signed": False,
                    "error": f"签到异常: {e}", "message": ""}
