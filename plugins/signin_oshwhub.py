"""
OSHWHub (立创开源硬件平台) 签到插件
基于 requests + Cookie 实现，无需 Playwright

签到流程：
1. 使用账号 Cookie 访问 /sign_in 检查签到状态
2. 若未签到，调用签到 API
3. 返回结果

签到 API 端点（基于 Next.js 路由推断）：
  GET  /api/user/sign/status   — 查询当日签到状态
  POST /api/user/sign/daily    — 执行签到
"""

import json, re
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
from core_signin import SigninBase, register


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

    def _get_headers(self) -> dict:
        """构造带 Cookie 的请求头"""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"{self.site_url}/sign_in",
            "Origin": self.site_url,
        }

    def signin(self) -> dict:
        """执行 OSHWHub 每日签到"""
        if not self.cookie:
            return {"success": False, "already_signed": False,
                    "error": "缺少 Cookie", "message": ""}

        try:
            import requests as _req
            headers = self._get_headers()

            # ── Step 1: 先访问 /sign_in 页面，获取签到状态 ──
            sign_page_url = f"{self.site_url}/sign_in"
            resp = _req.get(sign_page_url, headers=headers, timeout=15)

            if resp.status_code != 200:
                return {"success": False, "already_signed": False,
                        "error": f"访问签到页失败: HTTP {resp.status_code}", "message": ""}

            # 检查 Cookie 是否有效（是否跳转到登录页）
            if "login" in resp.url.lower() or "passport" in resp.url.lower():
                return {"success": False, "already_signed": False,
                        "error": "Cookie 已过期，请重新登录", "message": ""}

            # ── Step 2: 尝试从页面中提取签到状态 ──
            # 方法1：检查页面文本中是否有"已签到"提示
            if "已签到" in resp.text:
                return {"success": True, "already_signed": True,
                        "error": "", "message": "今天已签到 ✅"}

            # 方法2：尝试调用签到 API（多个候选端点）
            api_endpoints = [
                f"{self.site_url}/api/user/sign/daily",
                f"{self.site_url}/api/sign/daily",
                f"{self.site_url}/api/user/checkin",
                f"{self.site_url}/api/user/sign",
            ]

            for api_url in api_endpoints:
                try:
                    sign_resp = _req.post(
                        api_url,
                        headers={**headers, "Content-Type": "application/json",
                                 "X-Requested-With": "XMLHttpRequest"},
                        json={},
                        timeout=10,
                    )
                    result = self._parse_sign_response(sign_resp)
                    if result:
                        return result
                except Exception:
                    continue

            # 所有 API 端点都失败，回退到页面检测
            return {"success": False, "already_signed": False,
                    "error": "无法定位签到 API（网站可能改版）", "message": ""}

        except Exception as e:
            return {"success": False, "already_signed": False,
                    "error": f"签到异常: {e}", "message": ""}

    def _parse_sign_response(self, resp) -> Optional[dict]:
        """解析签到 API 响应"""
        text = resp.text.strip()

        # 检查 HTTP 状态
        if resp.status_code == 200 and text:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    success = data.get("success", False) or data.get("code") == 200
                    msg = data.get("message", "") or data.get("msg", "")
                    if success:
                        if "已签到" in msg or "already" in msg.lower():
                            return {"success": True, "already_signed": True,
                                    "error": "", "message": "今天已签到 ✅"}
                        return {"success": True, "already_signed": False,
                                "error": "", "message": msg or "签到成功 ✅"}
                    if "已签到" in msg:
                        return {"success": True, "already_signed": True,
                                "error": "", "message": "今天已签到 ✅"}
                    return {"success": False, "already_signed": False,
                            "error": msg or f"签到失败: HTTP {resp.status_code}"}
            except ValueError:
                pass

        # 非 JSON 响应 — 检查文本
        text_lower = text.lower()
        if "已签到" in text or "签到成功" in text:
            return {"success": True, "already_signed": "已签到" not in text,
                    "error": "", "message": "签到成功 ✅" if "签到成功" in text else "今天已签到 ✅"}
        if "login" in resp.url.lower():
            return {"success": False, "already_signed": False,
                    "error": "Cookie 无效，请重新登录", "message": ""}

        return None
