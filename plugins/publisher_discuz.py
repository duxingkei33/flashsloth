"""
Discuz! Publisher — 发帖 + 密码/验证码登录 + Cookie 方式
支持两种登录方式：
  1. Cookie 方式：用户从浏览器复制 Cookie 粘贴
  2. 密码+验证码方式：输入用户名密码，由用户填写验证码图片
使用人机浏览器模拟，避免反爬
"""
import re, json, time, random
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from flashsloth.plugins.browser_session import HumanSession


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
        self.fid = config.get("fid", "")
        self.login_mode = config.get("login_mode", "cookie")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        # 使用人机浏览器
        self.browser = HumanSession(base_url=self.site_url, min_delay=0.5, max_delay=2.0)
        raw_cookie = config.get("cookie", "")
        if raw_cookie:
            self.browser.set_cookies(raw_cookie)
        self._last_forum_page = ""  # 记录上次访问的板块页

    def _get_domain(self) -> str:
        return self.site_url.replace("https://", "").replace("http://", "").split("/")[0]

    def validate_config(self) -> list[str]:
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
        """测试连接 — 模拟真人访问验证"""
        if self.login_mode == "cookie":
            return self._test_cookie()
        else:
            return {
                "success": False,
                "error": "密码模式需先验证验证码才能测试登录",
                "needs_captcha": True,
            }

    def _test_cookie(self) -> dict:
        """测试 Cookie — 模拟真人访问个人主页"""
        try:
            # 先访问首页模拟入口
            self.browser.get("/forum.php")
            # 再访问个人主页（真人操作：首页→个人主页）
            resp = self.browser.get("/home.php?mod=space&do=profile")
            if "个人主页" in resp.text or self.username in resp.text:
                return {"success": True, "error": "", "status": "已登录"}
            for cookie in self.browser.session.cookies:
                if "auth" in cookie.name.lower():
                    return {"success": True, "error": "", "status": "已登录"}
            if "login" in resp.url.lower():
                return {"success": False, "error": "Cookie 已过期，请重新登录获取", "status": "Cookie过期"}
            return {"success": False, "error": "无法确认登录状态", "status": "未知"}
        except Exception as e:
            return {"success": False, "error": f"连接失败: {e}", "status": "连接失败"}

    def login_with_password(self, captcha_text: str, seccodehash: str) -> dict:
        """密码+验证码登录"""
        try:
            # 1. 先访问首页
            self.browser.get("/forum.php")
            # 2. 访问登录页
            r = self.browser.get("/member.php?mod=logging&action=login")
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

            # 3. 验证验证码
            check_url = f"{self.site_url}/misc.php?mod=seccode&action=check&inajax=1"
            check_resp = self.browser.post(
                check_url,
                data={"secverify": captcha_text, "idhash": seccodehash},
            )
            if "succeed" not in check_resp.text:
                return {"success": False, "error": "验证码错误，请重新填写"}

            # 4. 提交登录
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
            resp = self.browser.post(login_url, data=login_data)

            auth = [c for c in self.browser.session.cookies if "auth" in c.name.lower()]
            if auth:
                return {"success": True, "error": "", "status": "已登录"}
            err_msg = self._extract_error(resp.text)
            return {"success": False, "error": err_msg, "status": "登录失败"}
        except Exception as e:
            return {"success": False, "error": f"登录异常: {e}", "status": "异常"}

    def _extract_error(self, html: str) -> str:
        """从响应中提取错误信息"""
        patterns = [
            r'<div[^>]*class="alert_error"[^>]*>(.*?)</div>',
            r'<p[^>]*class="alert_info"[^>]*>(.*?)</p>',
            r'<div[^>]*id="messagetext"[^>]*>(.*?)</div>',
        ]
        for p in patterns:
            m = re.search(p, html, re.DOTALL)
            if m:
                text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if text and len(text) < 500:
                    return text
        # 尝试从提示信息页面提取
        msg = re.search(r'<div[^>]*class="c"[^>]*>(.*?)<div', html, re.DOTALL)
        if msg:
            text = re.sub(r"<[^>]+>", " ", msg.group(1)).strip()
            if text and len(text) < 500:
                return text
        return "未知错误"

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        if self.login_mode == "password":
            return {"success": False, "error": "请先完成验证码登录后再发帖",
                    "url": "", "id": ""}

        if not self._check_login():
            return {"success": False, "error": "Cookie 无效或已过期，请重新登录",
                    "url": "", "id": ""}

        fid = kwargs.get("fid", self.fid)
        if not fid:
            return {"success": False, "error": "请选择要发布到的版块",
                    "url": "", "id": ""}

        try:
            result = self._publish_thread(article, fid)
            return result
        except Exception as e:
            return {"success": False, "error": f"Discuz! 发布异常: {e}",
                    "url": "", "id": ""}

    def _check_login(self) -> bool:
        """模拟真人检查登录状态"""
        try:
            # 先访问首页
            self.browser.get("/forum.php")
            resp = self.browser.get("/home.php?mod=space&do=profile")
            if "个人主页" in resp.text or self.username in resp.text:
                return True
            for cookie in self.browser.session.cookies:
                if "auth" in cookie.name.lower():
                    return True
            return "login" not in resp.url.lower()
        except:
            return False

    def _get_formhash(self, fid: str) -> str | None:
        """获取发帖表单的 formhash"""
        try:
            url = f"/forum.php?mod=post&action=newthread&fid={fid}"
            # 模拟真人：先访问板块页，再点发帖
            forum_url = f"/forum.php?mod=forumdisplay&fid={fid}"
            self.browser.get(forum_url)
            resp = self.browser.get(url)
            for pattern in [
                r'name="formhash"[^>]+value="([^"]+)"',
                r'formhash\s*=\s*"([^"]+)"',
                r'formhash=([a-zA-Z0-9]+)',
            ]:
                match = re.search(pattern, resp.text)
                if match:
                    return match.group(1)
            return None
        except:
            return None

    def _extract_form_fields(self, html: str) -> dict:
        """提取发帖表单中的所有字段（含隐藏字段）"""
        fields = {}
        form_section = re.search(
            r'<form[^>]*id="postform"[^>]*>(.*?)</form>', html, re.DOTALL
        )
        if not form_section:
            form_section = re.search(
                r'<form[^>]*method="post"[^>]*>(.*?)</form>', html, re.DOTALL
            )
        if form_section:
            for m in re.finditer(
                r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"[^>]*>',
                form_section.group(1)
            ):
                fields[m.group(1)] = m.group(2)
            for m in re.finditer(
                r'<textarea[^>]*name="([^"]*)"[^>]*>(.*?)</textarea>',
                form_section.group(1), re.DOTALL
            ):
                if m.group(1) not in fields:
                    fields[m.group(1)] = m.group(2)
        return fields

    def _get_thread_categories(self, fid: str) -> list[dict]:
        """获取板块的主题分类（typeid）"""
        try:
            resp = self.browser.get(f"/forum.php?mod=post&action=newthread&fid={fid}")
            select = re.search(
                r'<select[^>]*name="typeid"[^>]*>(.*?)</select>',
                resp.text, re.DOTALL
            )
            if select:
                categories = []
                for m in re.finditer(
                    r'<option[^>]*value="(\d+)"[^>]*>(.*?)</option>',
                    select.group(1), re.DOTALL
                ):
                    name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                    if m.group(1) != "0" and name:
                        categories.append({"id": m.group(1), "name": name})
                return categories
            return []
        except:
            return []

    def _publish_thread(self, article: Article, fid: str) -> dict:
        """完整发帖流程：模拟真人操作"""
        # 第1步：导航到论坛首页
        self.browser.get("/forum.php")

        # 第2步：访问发帖页面，提取所有表单字段
        post_url = f"/forum.php?mod=post&action=newthread&fid={fid}"
        resp = self.browser.get(post_url)

        # 提取 formhash
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
            return {"success": False, "error": "无法获取 formhash，请检查版块 ID",
                    "url": "", "id": ""}

        # 提取表单隐藏字段
        form_fields = self._extract_form_fields(resp.text)

        # 检查是否需要主题分类
        categories = self._get_thread_categories(fid)
        typeid = ""
        if categories:
            # 如果有分类，选第一个可用
            typeid = categories[0]["id"]

        # 第3步：组装表单数据
        data = {
            "formhash": formhash,
            "posttime": form_fields.get("posttime", ""),
            "wysiwyg": "0",
            "subject": article.title,
            "message": article.to_html(),
            "typeid": typeid or form_fields.get("typeid", ""),
            "readperm": form_fields.get("readperm", ""),
            "price": form_fields.get("price", "0"),
            "allownoticeauthor": "1",
            "replycredit_extcredits": "0",
            "replycredit_times": "1",
            "replycredit_membertimes": "1",
            "replycredit_random": "100",
        }
        # 合并从表单提取的其他字段
        for key in form_fields:
            if key not in data:
                data[key] = form_fields[key]

        # 第4步：提交帖子
        submit_url = (
            f"{self.site_url}/forum.php?mod=post&action=newthread"
            f"&fid={fid}&extra=&topicsubmit=yes"
        )
        # 模拟真人输入后提交
        time.sleep(random.uniform(0.5, 1.5))
        resp = self.browser.post(submit_url, data=data)

        # 第5步：检查结果
        tid_match = re.search(r"tid=(\d+)", resp.url)
        if tid_match:
            tid = tid_match.group(1)
            return {
                "success": True,
                "tid": tid,
                "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                "error": "",
            }

        # 检查是否有 alert_error
        err_match = re.search(
            r'<div[^>]*class="alert_error"[^>]*>(.*?)</div>', resp.text, re.DOTALL
        )
        if err_match:
            return {"success": False, "error": err_match.group(1).strip()[:500],
                    "url": "", "id": ""}

        # 检查 messagetext（可能包含空错误）或提示信息
        msg_match = re.search(
            r'<div[^>]*id="messagetext"[^>]*>(.*?)</div>', resp.text, re.DOTALL
        )
        if msg_match:
            text = re.sub(r"<[^>]+>", "", msg_match.group(1)).strip()
            if text:
                return {"success": False, "error": text[:500], "url": "", "id": ""}

        # 检查 JS 跳转（发帖成功后可能通过 JS 跳转）
        js_match = re.search(
            r'window\.location\s*=\s*["\']([^"\']+)["\']', resp.text
        )
        if js_match:
            redirect_url = js_match.group(1)
            if not redirect_url.startswith("http"):
                redirect_url = self.site_url + "/" + redirect_url.lstrip("/")
            # 跟进 JS 跳转
            time.sleep(1)
            r2 = requests.get(redirect_url, timeout=15)
            tid = re.search(r"tid=(\d+)", r2.url)
            if tid:
                return {
                    "success": True,
                    "tid": tid.group(1),
                    "url": r2.url,
                    "error": "",
                }
            return {"success": True, "tid": "", "url": redirect_url, "error": ""}

        if "发新主题" not in resp.text and "发表回复" not in resp.text:
            # 可能成功了但没有 tid（某些论坛配置）
            return {"success": True, "tid": "", "url": self.site_url, "error": ""}

        return {"success": False, "error": "发帖失败，请检查版块权限或是否有主题分类未选择",
                "url": "", "id": ""}
