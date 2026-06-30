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
try:
    from flashsloth.plugins.browser_session import HumanSession
except ImportError:
    from plugins.browser_session import HumanSession


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

    def _md_to_html(self, md_text: str) -> str:
        """简单的 Markdown 到 HTML 转换（无需安装 markdown 包）"""
        import html as html_mod
        text = html_mod.escape(md_text)
        # 代码块
        text = re.sub(r'```(\w*)\n(.*?)```', r'<pre><code>\2</code></pre>', text, flags=re.DOTALL)
        # 行内代码
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        # 粗体
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.*?)__', r'<strong>\1</strong>', text)
        # 斜体
        text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(.*?)_', r'<em>\1</em>', text)
        # 图片
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1">', text)
        # 链接
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        # 标题
        text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        # 列表
        text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        text = re.sub(r'^\* (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        # 段落
        parts = []
        for para in text.split('\n\n'):
            para = para.strip()
            if para and not para.startswith('<'):
                para = f'<p>{para}</p>'
            if para:
                parts.append(para)
        return '\n'.join(parts)

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

    def _verify_thread_exists(self, tid: str, title: str = "") -> dict:
        """验证帖子真实状态：可见、待审核、不存在

        像人一样去个人中心→我的帖子双重确认
        """
        try:
            resp = self.browser.get(f"/forum.php?mod=viewthread&tid={tid}")
            body_class = re.search(r'class="pg_(\w+)"', resp.text)
            page_class = body_class.group(1) if body_class else ""

            # 页面特征判断
            if "viewthread" in resp.url and "tid" in resp.url:
                if "审核" in resp.text or "待审核" in resp.text:
                    return {"status": "pending_review", "visible": False,
                            "title": "帖子已提交，等待审核"}
                if "抱歉" in resp.text[:500] or "没有找到" in resp.text[:500]:
                    return {"status": "not_found", "visible": False,
                            "title": "帖子未找到（可能已被删除或审核中）"}
                url = resp.url
                title_m = re.search(r"<title>(.*?)</title>", resp.text)
                title_text = title_m.group(1) if title_m else ""

                # 双重确认：去个人中心→我的帖子看看
                try:
                    from plugins.forum_reader import DiscuzForumReader
                    site_url = self.config.get("site_url", "").rstrip("/")
                    cookie = self.config.get("cookie", "")
                    reader = DiscuzForumReader(site_url, cookies=cookie,
                                               username=self.username)
                    my_posts = reader.check_thread_in_my_posts(tid, title or title_text)
                    if my_posts["status"] == "published":
                        return {"status": "published", "visible": True,
                                "url": url, "title": title_text,
                                "my_posts_verified": True}
                    elif my_posts["status"] == "pending_review":
                        return {"status": "pending_review", "visible": False,
                                "title": "帖子不在'我的帖子'列表中，但直接访问可见（可能审核中）",
                                "my_posts_verified": False}
                except Exception:
                    pass  # 降级为直接验证结果

                return {"status": "published", "visible": True,
                        "url": url, "title": title_text}

            if "login" in resp.url.lower():
                return {"status": "login_required", "visible": False,
                        "title": "需重新登录"}

            return {"status": "unknown", "visible": False,
                    "title": f"状态不明 (page: {page_class}, url: {resp.url})"}
        except Exception as e:
            return {"status": "error", "visible": False, "title": str(e)}

    def _check_duplicate_title(self, fid: str, title: str) -> bool:
        """检查论坛最近帖子中是否已有相同标题（去重）"""
        try:
            resp = self.browser.get(
                f"/forum.php?mod=forumdisplay&fid={fid}"
                f"&filter=lastpost&orderby=lastpost"
            )
            # 检查 mydigit.cn 格式
            for m in re.finditer(
                r'href="thread-\d+-1-1\.html"[^>]*>(.*?)</a>',
                resp.text, re.DOTALL
            ):
                existing = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if existing.lower() == title.lower()[:30]:
                    return True
            # 标准 Discuz 格式
            for m in re.finditer(
                r'href="[^"]*viewthread[^"]*tid=(\d+)"[^>]*>(.*?)</a>',
                resp.text, re.DOTALL
            ):
                existing = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                if existing.lower() == title.lower()[:30]:
                    return True
            return False
        except:
            return False

    def _publish_thread(self, article: Article, fid: str) -> dict:
        """完整发帖流程：模拟真人操作"""
        # 第0步：去重检查
        if self._check_duplicate_title(fid, article.title):
            return {"success": False,
                    "error": f"该标题已在 fid={fid} 中存在（去重），跳过发布",
                    "url": "", "id": "", "message": "skip_duplicate"}

        # 第1步：导航到论坛首页
        self.browser.get("/forum.php")

        # 第2步：访问发帖页面
        post_url = f"/forum.php?mod=post&action=newthread&fid={fid}"
        resp = self.browser.get(post_url)

        # 检测发帖页面是否正常（是否有 formhash）
        body_class = re.search(r'class="pg_(\w+)"', resp.text)
        page_class = body_class.group(1) if body_class else ""

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
            # 尝试从页面提取错误信息
            msg = ""
            for cls in ["alert_error", "alert_info"]:
                m = re.search(f'<div[^>]*class="{cls}"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
                if m:
                    msg = re.sub(r"<[^>]+>", " ", m.group(1)).strip()[:200]
                    break
            if not msg:
                msg_text = re.search(r'<div[^>]*id="messagetext"[^>]*>(.*?)</div>', resp.text, re.DOTALL)
                if msg_text:
                    msg = re.sub(r"<[^>]+>", " ", msg_text.group(1)).strip()[:200]
            if not msg and "提示信息" in resp.text:
                msg = "账号无发帖权限（提示信息页面，无发帖表单）"
            if not msg:
                msg = f"无法获取发帖表单 (page: {page_class})，请检查账号权限"
            return {"success": False, "error": msg, "url": "", "id": ""}

        # 提取表单隐藏字段
        form_fields = self._extract_form_fields(resp.text)

        # 检查是否需要主题分类
        categories = self._get_thread_categories(fid)
        typeid = ""
        if categories:
            typeid = categories[0]["id"]

        # 第3步：组装表单数据
        body_html = self._md_to_html(article.body) if article.body else ""
        data = {
            "formhash": formhash,
            "posttime": form_fields.get("posttime", ""),
            "wysiwyg": "0",
            "subject": article.title,
            "message": body_html,
            "typeid": typeid or form_fields.get("typeid", ""),
            "readperm": form_fields.get("readperm", ""),
            "price": form_fields.get("price", "0"),
            "allownoticeauthor": "1",
            "replycredit_extcredits": "0",
            "replycredit_times": "1",
            "replycredit_membertimes": "1",
            "replycredit_random": "100",
        }
        for key in form_fields:
            if key not in data:
                data[key] = form_fields[key]

        # 第4步：提交帖子
        submit_url = (
            f"{self.site_url}/forum.php?mod=post&action=newthread"
            f"&fid={fid}&extra=&topicsubmit=yes"
        )
        time.sleep(random.uniform(0.5, 1.5))
        resp = self.browser.post(submit_url, data=data)

        # 第5步：分析响应状态
        response_page_class = ""
        bc = re.search(r'class="pg_(\w+)"', resp.text)
        if bc:
            response_page_class = bc.group(1)

        # 检查是否有 tid 在 URL 中
        tid_match = re.search(r"tid=(\d+)", resp.url)
        if tid_match:
            tid = tid_match.group(1)
            # 验证帖子的真实状态
            time.sleep(1.5)  # 等论坛处理
            verify = self._verify_thread_exists(tid, title=article.title)
            if verify["status"] == "published":
                return {
                    "success": True, "tid": tid,
                    "url": verify.get("url", resp.url),
                    "error": "", "message": "published",
                }
            elif verify["status"] == "pending_review":
                return {
                    "success": True, "tid": tid,
                    "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                    "error": "帖子已发布，等待管理员审核",
                    "message": "pending_review",
                }
            else:
                return {
                    "success": True, "tid": tid,
                    "url": f"{self.site_url}/forum.php?mod=viewthread&tid={tid}",
                    "error": f"已创建但状态不明: {verify.get('title', '')}",
                    "message": "uncertain",
                }

        # 没有 tid，检查错误
        if response_page_class == "index":
            return {"success": False,
                    "error": "发帖后跳转回首页，帖子可能已创建但不可见，或账号无权限。请检查账号发帖权限",
                    "url": "", "id": ""}

        # 检查 alert_error（真正的错误）
        err_match = re.search(
            r'<div[^>]*class="alert_error"[^>]*>(.*?)</div>', resp.text, re.DOTALL
        )
        if err_match:
            return {"success": False, "error": err_match.group(1).strip()[:500],
                    "url": "", "id": ""}

        # 检查 JS 跳转（发帖成功，可能需审核或自动跳转到帖子页）
        js_match = re.search(
            r'window\.location(?:\.href)?\s*=\s*["\']([^"\']+)["\']', resp.text
        )
        if js_match:
            redirect_url = js_match.group(1)
            if not redirect_url.startswith("http"):
                redirect_url = self.site_url + "/" + redirect_url.lstrip("/")
            time.sleep(1)
            import requests as req_mod
            r2 = req_mod.get(redirect_url, timeout=15)
            # 支持两种 URL 格式：tid=123 和 thread-123-1-1.html
            tid = re.search(r"tid=(\d+)", r2.url) or re.search(r"thread-(\d+)-", r2.url)
            if tid:
                return {"success": True, "tid": tid.group(1),
                        "url": r2.url, "error": "", "message": "js_redirect"}
            return {"success": True, "tid": "", "url": redirect_url,
                    "error": "JS跳转后未找到tid", "message": "js_redirect_no_tid"}

        if response_page_class == "viewthread":
            # 已经在帖子页面（无重定向的情况）
            tid_in_body = re.search(r"tid=(\d+)", resp.text)
            if tid_in_body:
                return {"success": True, "tid": tid_in_body.group(1),
                        "url": resp.url, "error": "", "message": "direct_viewthread"}
            return {"success": True, "tid": "", "url": resp.url,
                    "error": "", "message": "viewthread_no_tid"}

        return {"success": False,
                "error": f"发帖失败 (page: {response_page_class})，请检查版块权限或主题分类",
                "url": "", "id": ""}
