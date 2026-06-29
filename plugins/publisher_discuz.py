"""
Discuz! Publisher — Cookie 方式发帖
适用场景：用户自行登录论坛后复制 Cookie，插件用有效 Cookie 直接发帖
"""
import re, requests, json
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class DiscuzPublisher(Publisher):
    name = "discuz"
    display_name = "Discuz! 论坛"
    config_fields = [
        {"key": "site_url", "label": "论坛地址", "type": "text", "required": True,
         "placeholder": "https://www.amobbs.com"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录后从浏览器 F12 复制 Cookie"},
        {"key": "fid", "label": "版块 ID", "type": "text", "required": True,
         "placeholder": "发帖目标版块的 fid，如 42"},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.site_url = config.get("site_url", "").rstrip("/")
        self.fid = config.get("fid", "")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        })
        # 解析 Cookie 字符串
        raw_cookie = config.get("cookie", "")
        for item in raw_cookie.split(";"):
            item = item.strip()
            if "=" in item:
                key, val = item.split("=", 1)
                self.session.cookies.set(key.strip(), val.strip(), domain=self._get_domain())

    def _get_domain(self) -> str:
        """从 site_url 提取域名"""
        return self.site_url.replace("https://", "").replace("http://", "").split("/")[0]

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        # 验证 Cookie 有效性
        if not self._check_login():
            return {"success": False, "error": "Cookie 无效或已过期，请重新登录后复制 Cookie",
                    "url": "", "id": ""}

        try:
            # 获取 formhash
            formhash = self._get_formhash()
            if not formhash:
                return {"success": False, "error": "无法获取 formhash，请检查版块 ID",
                        "url": "", "id": ""}

            # 发帖
            html_body = article.to_html()
            result = self._post_thread(formhash, article.title, html_body)

            if result["success"]:
                return {
                    "success": True,
                    "url": result.get("url", ""),
                    "id": result.get("tid", ""),
                    "error": "",
                }
            return result

        except Exception as e:
            return {"success": False, "error": f"Discuz! 发布异常: {e}",
                    "url": "", "id": ""}

    def _check_login(self) -> bool:
        """检查 Cookie 是否有效（访问个人主页）"""
        resp = self.session.get(f"{self.site_url}/home.php?mod=space&do=profile", timeout=10)
        # 登录后页面含有用户名或 uid
        if "个人主页" in resp.text or "space.php" in resp.url:
            return True
        # 检查 Cookie 中是否有 auth
        for cookie in self.session.cookies:
            if "auth" in cookie.name.lower():
                return True
        return "login" not in resp.url.lower()

    def _get_formhash(self) -> str | None:
        """进入发帖页面获取 formhash"""
        post_url = f"{self.site_url}/forum.php?mod=post&action=newthread&fid={self.fid}"
        resp = self.session.get(post_url, timeout=15)
        for pattern in [
            r'name="formhash"[^>]+value="([^"]+)"',
            r'formhash\s*=\s*"([^"]+)"',
            r'formhash=([a-zA-Z0-9]+)',
        ]:
            match = re.search(pattern, resp.text)
            if match:
                return match.group(1)
        return None

    def _post_thread(self, formhash: str, title: str, content_html: str) -> dict:
        """发表新主题"""
        post_url = f"{self.site_url}/forum.php?mod=post&action=newthread&fid={self.fid}&extra=&topicsubmit=yes"
        data = {
            "formhash": formhash,
            "posttime": "",
            "wysiwyg": "0",
            "subject": title,
            "message": content_html,
            "readperm": "",
            "price": "0",
            "allownoticeauthor": "1",
            "replycredit_extcredits": "0",
            "replycredit_times": "1",
            "replycredit_membertimes": "1",
            "replycredit_random": "100",
        }
        resp = self.session.post(post_url, data=data, timeout=30, allow_redirects=True)

        # 发帖成功会跳转到新帖子页面
        tid_match = re.search(r"tid=(\d+)", resp.url)
        if tid_match:
            tid = tid_match.group(1)
            return {
                "success": True,
                "tid": tid,
                "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                "error": "",
            }

        # 检查错误提示
        err_match = re.search(
            r'<div[^>]*class="alert_error"[^>]*>([\s\S]*?)</div>', resp.text
        )
        if err_match:
            return {"success": False, "error": err_match.group(1).strip()[:200],
                    "url": "", "id": ""}

        # 没报错可能成功了
        if "发新主题" not in resp.text and "发表回复" not in resp.text:
            return {"success": True, "tid": "", "url": self.site_url, "error": ""}

        return {"success": False, "error": "发帖失败，请检查版块 ID 和权限",
                "url": "", "id": ""}
