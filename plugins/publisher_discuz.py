"""
Discuz! Publisher — 发帖 + 密码/验证码登录 + Cookie 方式
支持两种登录方式：
  1. Cookie 方式：用户从浏览器复制 Cookie 粘贴
  2. 密码+验证码方式：输入用户名密码，由用户填写验证码图片
添加账号时自动验证登录状态，失败显示具体原因。
"""
import re, requests, json, time
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class DiscuzPublisher(Publisher):
    name = "discuz"
    display_name = "Discuz! 论坛"
    config_fields = [
        {"key": "login_mode", "label": "登录方式", "type": "select", "required": True,
         "options": [
             {"value": "cookie", "label": "Cookie 直接发帖"},
             {"value": "password", "label": "密码+验证码登录"},
         ],
         "placeholder": "选择登录方式"},
        {"key": "site_url", "label": "论坛地址", "type": "text", "required": True,
         "placeholder": "https://www.amobbs.com"},
        {"key": "username", "label": "用户名（密码模式）", "type": "text", "required": False,
         "placeholder": "论坛登录用户名"},
        {"key": "password", "label": "密码（密码模式）", "type": "password", "required": False,
         "placeholder": "论坛登录密码"},
        {"key": "cookie", "label": "Cookie（Cookie模式）", "type": "password", "required": False,
         "placeholder": "登录后从浏览器 F12 复制 Cookie"},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.site_url = config.get("site_url", "").rstrip("/")
        self.fid = config.get("fid", "")  # 兼容旧配置，新配置在 publish() 时传入
        self.login_mode = config.get("login_mode", "cookie")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
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
        return self.site_url.replace("https://", "").replace("http://", "").split("/")[0]

    def validate_config(self) -> list[str]:
        """验证配置完整性"""
        missing = []
        if not self.site_url:
            missing.append("论坛地址")
        if self.login_mode == "cookie" and not self.config.get("cookie", ""):
            missing.append("Cookie")
        if self.login_mode == "password" and not self.username:
            missing.append("用户名")
        if self.login_mode == "password" and not self.password:
            missing.append("密码")
        return missing

    def test_connection(self) -> dict:
        """测试连接状态 — 验证登录是否有效，返回详细结果"""
        if self.login_mode == "cookie":
            return self._test_cookie()
        else:
            return {
                "success": False,
                "error": "密码模式需先验证验证码才能测试登录",
                "needs_captcha": True,
            }

    def _test_cookie(self) -> dict:
        """测试 Cookie 是否有效"""
        try:
            resp = self.session.get(
                f"{self.site_url}/home.php?mod=space&do=profile", timeout=10
            )
            if "个人主页" in resp.text or self.username in resp.text:
                return {"success": True, "error": "", "status": "已登录"}
            for cookie in self.session.cookies:
                if "auth" in cookie.name.lower():
                    return {"success": True, "error": "", "status": "已登录"}
            if "login" in resp.url.lower():
                return {"success": False, "error": "Cookie 已过期，请重新登录获取", "status": "Cookie过期"}
            return {"success": False, "error": "无法确认登录状态", "status": "未知"}
        except Exception as e:
            return {"success": False, "error": f"连接失败: {e}", "status": "连接失败"}

    def login_with_password(self, captcha_text: str, seccodehash: str) -> dict:
        """密码+验证码登录，返回详细结果"""
        try:
            # 1. 获取登录页
            r = self.session.get(
                f"{self.site_url}/member.php?mod=logging&action=login", timeout=20
            )
            formhash = re.search(r'name="formhash"\s+value="([^"]+)"', r.text)
            if not formhash:
                return {"success": False, "error": "无法获取登录表单"}
            formhash = formhash.group(1)

            form_action = re.search(
                r'<form[^>]*name="login"[^>]*action="([^"]*)"', r.text
            )
            if not form_action:
                return {"success": False, "error": "无法获取登录 action"}
            loginhash = re.search(r"loginhash=([a-zA-Z0-9]+)", form_action.group(1))
            loginhash = loginhash.group(1) if loginhash else ""

            # 2. 先验证验证码
            check_url = f"{self.site_url}/misc.php?mod=seccode&action=check&inajax=1"
            check_resp = self.session.post(
                check_url, data={"secverify": captcha_text, "idhash": seccodehash}, timeout=10
            )
            if "succeed" not in check_resp.text:
                return {"success": False, "error": "验证码错误，请重新填写"}

            # 3. 登录
            login_url = (
                f"{self.site_url}/member.php?mod=logging&action=login"
                f"&loginsubmit=yes&loginhash={loginhash}"
            )
            login_data = {
                "formhash": formhash,
                "referer": self.site_url + "/",
                "loginfield": "username",
                "username": self.username,
                "password": self.password,
                "questionid": "0",
                "answer": "",
                "seccodehash": seccodehash,
                "seccodemodid": "member::logging",
                "seccodeverify": captcha_text,
                "cookietime": "2592000",
            }
            resp = self.session.post(login_url, data=login_data, timeout=20, allow_redirects=True)

            # 4. 检查结果
            auth = [c for c in self.session.cookies if "auth" in c.name.lower()]
            if auth:
                return {"success": True, "error": "", "status": "已登录"}
            
            err_msg = self._extract_error(resp.text)
            return {"success": False, "error": err_msg, "status": "登录失败"}
        except Exception as e:
            return {"success": False, "error": f"登录异常: {e}", "status": "异常"}

    def _extract_error(self, html: str) -> str:
        """从登录响应 HTML 提取错误信息"""
        patterns = [
            r'<div[^>]*class="alert_error"[^>]*>([\s\S]*?)</div>',
            r'<p[^>]*class="alert_info"[^>]*>(.*?)</p>',
            r'<p[^>]*>(.*?)(?:</p>)',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if text and len(text) < 300:
                    return text
        return "未知错误"

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        # 密码模式需要先确认已登录
        if self.login_mode == "password":
            return {"success": False, "error": "请先完成验证码登录后再发帖",
                    "url": "", "id": ""}

        # 验证 Cookie 有效性
        if not self._check_login():
            return {"success": False, "error": "Cookie 无效或已过期，请重新登录",
                    "url": "", "id": ""}

        # 优先使用发布时传入的 fid，其次使用配置中的 fid
        fid = kwargs.get("fid", self.fid)
        if not fid:
            return {"success": False, "error": "请选择要发布到的版块",
                    "url": "", "id": ""}

        try:
            formhash = self._get_formhash(fid)
            if not formhash:
                return {"success": False, "error": f"无法获取 formhash，请检查版块 ID ({fid})",
                        "url": "", "id": ""}

            html_body = article.to_html()
            result = self._post_thread(formhash, article.title, html_body, fid)

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
        resp = self.session.get(f"{self.site_url}/home.php?mod=space&do=profile", timeout=10)
        if "个人主页" in resp.text or self.username in resp.text:
            return True
        for cookie in self.session.cookies:
            if "auth" in cookie.name.lower():
                return True
        return "login" not in resp.url.lower()

    def _get_formhash(self, fid: str = None) -> str | None:
        fid = fid or self.fid
        post_url = f"{self.site_url}/forum.php?mod=post&action=newthread&fid={fid}"
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

    def _post_thread(self, formhash: str, title: str, content_html: str, fid: str = None) -> dict:
        fid = fid or self.fid
        post_url = (
            f"{self.site_url}/forum.php?mod=post&action=newthread"
            f"&fid={fid}&extra=&topicsubmit=yes"
        )
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

        tid_match = re.search(r"tid=(\d+)", resp.url)
        if tid_match:
            tid = tid_match.group(1)
            return {
                "success": True,
                "tid": tid,
                "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                "error": "",
            }

        err_match = re.search(
            r'<div[^>]*class="alert_error"[^>]*>([\s\S]*?)</div>', resp.text
        )
        if err_match:
            return {"success": False, "error": err_match.group(1).strip()[:200],
                    "url": "", "id": ""}

        if "发新主题" not in resp.text and "发表回复" not in resp.text:
            return {"success": True, "tid": "", "url": self.site_url, "error": ""}

        return {"success": False, "error": "发帖失败，请检查版块 ID 和权限",
                "url": "", "id": ""}
