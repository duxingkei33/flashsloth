"""
人机浏览器模拟 — 模拟真人操作，避免被论坛反爬封杀

⚠️ 已废弃（2026-07-06）：统一使用 Playwright + core/anti_detect.py
   不再使用 requests/curl/wget 做任何平台操作。
   此文件保留供参考，新代码禁止引用。
"""

import random, time, re, json
from typing import Optional
from urllib.parse import urljoin
import requests

# ─── 真实浏览器 UA 池 ───────────────────────────
_USER_AGENTS = [
    # Windows Chrome
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    # Windows Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Windows Firefox
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    # Mac Chrome
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

_ACCEPT_HTML = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
_ACCEPT_LANG = "zh-CN,zh;q=0.9,en;q=0.8"

# ─── 安全验证页面检测 ──────────────────────────
_SECURITY_PATTERNS = [
    r'security_session_verify',
    r'verify[_-]?session',
    r'安全检查',
    r'security.?check',
    r'human.?verify',
    r'browser.?check',
]


def _is_security_page(html: str) -> bool:
    """检测是否是安全验证页面"""
    lower = html.lower()[:5000]
    for pat in _SECURITY_PATTERNS:
        if re.search(pat, lower):
            return True
    return False


def _try_auto_verify(session: requests.Session, page_url: str) -> bool:
    """自动通过已知的安全验证（如 security_session_verify）"""
    # Discuz! 安全验证：页面通常包含一个自动提交的表单或JS
    # 尝试获取页面并检查是否有隐藏的验证表单
    try:
        resp = session.get(page_url, timeout=15)
        # 检查是否有 meta refresh
        mr = re.search(r'<meta[^>]*http-equiv="refresh"[^>]*content="(\d+);\s*url=([^"]+)"', resp.text, re.IGNORECASE)
        if mr:
            delay = int(mr.group(1))
            redirect_url = mr.group(2)
            if not redirect_url.startswith('http'):
                redirect_url = urljoin(page_url, redirect_url)
            time.sleep(min(delay + 0.5, 3))  # 模拟等待后跳转
            resp2 = session.get(redirect_url, timeout=15)
            return 'security' not in resp2.url.lower() and len(resp2.text) > 1000
        # 检查是否有自动提交的 form
        auto_form = re.search(
            r'<form[^>]*id="[^"]*"[^>]*>\s*<input[^>]*type="hidden"[^>]*>\s*</form>\s*<script[^>]*>\s*document\.\w+\[\'[^\']*\']\.submit\(\)',
            resp.text, re.DOTALL
        )
        if auto_form:
            form_data = {}
            for m in re.finditer(r'<input[^>]*type="hidden"[^>]*name="([^"]*)"[^>]*value="([^"]*)"', resp.text):
                form_data[m.group(1)] = m.group(2)
            if form_data:
                session.post(page_url, data=form_data, timeout=15)
                return True
        return False
    except:
        return False


# ─── 人机浏览器会话 ───────────────────────────
class HumanSession:
    """模拟真人浏览器会话"""

    def __init__(self, base_url: str = "", min_delay: float = 0.3, max_delay: float = 1.5):
        self._session = requests.Session()
        self._base_url = base_url.rstrip("/")
        self._last_url = ""
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._setup_headers()

    def _setup_headers(self):
        """设置真人浏览器 HTTP 头"""
        ua = random.choice(_USER_AGENTS)
        sec_ch = ""
        if "Chrome" in ua and "Edg" not in ua:
            sec_ch = '"Google Chrome";v="125", "Chromium";v="125", "Not=A?Brand";v="24"'
        elif "Edg" in ua:
            sec_ch = '"Microsoft Edge";v="125", "Chromium";v="125", "Not=A?Brand";v="24"'
        elif "Firefox" in ua:
            sec_ch = ""

        headers = {
            "User-Agent": ua,
            "Accept": _ACCEPT_HTML,
            "Accept-Language": _ACCEPT_LANG,
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        if sec_ch:
            headers["Sec-Ch-Ua"] = sec_ch
            headers["Sec-Ch-Ua-Mobile"] = "?0"
            headers["Sec-Ch-Ua-Platform"] = '"Windows"'
        self._session.headers.update(headers)

    def _human_delay(self, factor: float = 1.0):
        """模拟真人操作延迟"""
        delay = random.uniform(self._min_delay, self._max_delay) * factor
        time.sleep(delay)

    def _update_referer(self, url: str, method: str):
        """更新 Referer 链"""
        if method == "GET":
            self._session.headers["Referer"] = self._last_url or url
            self._last_url = url
        elif method == "POST":
            self._session.headers["Referer"] = self._last_url or url

    def set_cookies(self, cookies_text: str, domain: str = ""):
        """设置 Cookie 字符串（从浏览器复制）"""
        if not domain and self._base_url:
            domain = self._base_url.replace("https://", "").replace("http://", "").split("/")[0]
        for item in cookies_text.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self._session.cookies.set(k.strip(), v.strip(), domain=domain or self._get_domain())

    def _get_domain(self) -> str:
        if self._base_url:
            return self._base_url.replace("https://", "").replace("http://", "").split("/")[0]
        return ""

    def get(self, url: str, **kwargs) -> requests.Response:
        """真人 GET 请求"""
        full_url = urljoin(self._base_url + "/", url) if not url.startswith("http") else url
        self._human_delay()
        self._update_referer(full_url, "GET")
        resp = self._session.get(full_url, timeout=kwargs.pop("timeout", 15), **kwargs)
        self._last_url = full_url
        return resp

    def post(self, url: str, data: dict = None, **kwargs) -> requests.Response:
        """真人 POST 请求"""
        full_url = urljoin(self._base_url + "/", url) if not url.startswith("http") else url
        self._human_delay(1.5)  # 提交表单延迟稍长
        kwargs.setdefault("timeout", 30)
        self._update_referer(full_url, "POST")
        # 模拟输入时间
        if data and "message" in data:
            time.sleep(random.uniform(0.5, 2.0))
        if data and "subject" in data:
            time.sleep(random.uniform(0.2, 0.8))
        resp = self._session.post(full_url, data=data, **kwargs)
        self._last_url = full_url
        return resp

    def navigate(self, url: str) -> requests.Response:
        """模拟完整页面导航：依次访问首页→目标页"""
        full_url = urljoin(self._base_url + "/", url) if not url.startswith("http") else url
        # 如果不是同一域名，先访问首页
        if self._base_url and not url.startswith(self._base_url):
            self.get(self._base_url + "/")
        return self.get(full_url)

    def get_formhash(self, page_url: str) -> Optional[str]:
        """获取 Discuz! 表单的 formhash"""
        resp = self.get(page_url)
        for pattern in [
            r'name="formhash"[^>]+value="([^"]+)"',
            r'formhash\s*=\s*"([^"]+)"',
            r'formhash=([a-zA-Z0-9]+)',
        ]:
            match = re.search(pattern, resp.text)
            if match:
                return match.group(1)
        return None

    def extract_form(self, html: str, form_id: str = "") -> dict:
        """提取表单中的所有字段（含隐藏字段）"""
        form_data = {}
        # 按 ID 或第一个 form
        if form_id:
            form_section = re.search(
                rf'<form[^>]*id="{form_id}"[^>]*>(.*?)</form>', html, re.DOTALL
            )
        else:
            form_section = re.search(r'<form[^>]*>(.*?)</form>', html, re.DOTALL)

        if not form_section:
            return form_data

        form_html = form_section.group(1)
        for m in re.finditer(
            r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"[^>]*>',
            form_html
        ):
            form_data[m.group(1)] = m.group(2)

        for m in re.finditer(
            r'<textarea[^>]*name="([^"]*)"[^>]*>(.*?)</textarea>',
            form_html, re.DOTALL
        ):
            if m.group(1) not in form_data:
                form_data[m.group(1)] = m.group(2)

        return form_data

    def ensure_logged_in(self, check_url: str = "", username: str = "") -> bool:
        """检查登录状态，如被踢出则自动处理"""
        url = check_url or f"{self._base_url}/home.php?mod=space&do=profile"
        try:
            resp = self.get(url)
            if username and username in resp.text:
                return True
            if "login" in resp.url.lower():
                return False
            return True
        except:
            return False

    def solve_security(self, page_url: str) -> bool:
        """尝试自动通过安全验证"""
        try:
            resp = self.get(page_url)
            if not _is_security_page(resp.text):
                return True  # 没有安全验证
            return _try_auto_verify(self._session, page_url)
        except:
            return False

    @property
    def session(self):
        return self._session

    @property
    def cookies(self):
        return dict(self._session.cookies)

    def close(self):
        self._session.close()
