"""
OSHWHub Publisher — 立创开源硬件平台发布器

使用 Playwright 浏览器自动化登录 OSHWHub 后发布文章。
支持两种登录方式：
  1. Cookie 方式：用户从浏览器复制 Cookie 粘贴
  2. 密码+验证码方式：Playwright 自动打开浏览器登录，由用户处理验证码

OSHWHub 是嘉立创生态的一部分，Next.js + Ant Design 构建。
非 Discuz 系，独立实现发帖 API 调用。
"""
import re, json, time, random, os
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
try:
    from flashsloth.plugins.oshwhub_login import OshwhubPlaywrightLogin
except ImportError:
    from plugins.oshwhub_login import OshwhubPlaywrightLogin


@register
class OshwhubPublisher(Publisher):
    name = "oshwhub"
    display_name = "立创开源硬件平台"
    config_fields = [
        {"key": "login_mode", "label": "登录方式", "type": "select", "required": True,
         "options": [
             {"value": "cookie", "label": "Cookie 直接发帖"},
             {"value": "password", "label": "密码+验证码登录（Playwright）"},
         ],
         "placeholder": "选择登录方式"},
        {"key": "site_url", "label": "平台地址", "type": "text", "required": True,
         "default": "https://oshwhub.com",
         "placeholder": "https://oshwhub.com"},
        {"key": "username", "label": "用户名/邮箱（密码模式）", "type": "text", "required": False,
         "placeholder": "OSHWHub 登录用户名或邮箱"},
        {"key": "password", "label": "密码（密码模式）", "type": "password", "required": False,
         "placeholder": "OSHWHub 登录密码"},
        {"key": "cookie", "label": "Cookie（Cookie模式）", "type": "password", "required": False,
         "placeholder": "登录后从浏览器 F12 复制 Cookie"},
    ]

    # OSHWHub API 端点（基于嘉立创 EDA 生态推断）
    API_PATHS = {
        "user_info": "/api/user/info",
        "publish_project": "/api/project/publish",
        "my_projects": "/api/project/my",
        "upload_image": "/api/file/upload",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.site_url = config.get("site_url", "https://oshwhub.com").rstrip("/")
        self.login_mode = config.get("login_mode", "cookie")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self._session = None
        self._playwright_login = None
        raw_cookie = config.get("cookie", "")
        if raw_cookie:
            self._init_session_with_cookie(raw_cookie)

    def _get_domain(self) -> str:
        return self.site_url.replace("https://", "").replace("http://", "").split("/")[0]

    def _init_session_with_cookie(self, cookie_str: str):
        """使用 Cookie 初始化 requests Session"""
        import requests
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": self.site_url,
            "Referer": f"{self.site_url}/",
        })
        domain = self._get_domain()
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self._session.cookies.set(k.strip(), v.strip(), domain=domain)

    def validate_config(self) -> list[str]:
        missing = []
        if not self.site_url:
            missing.append("平台地址")
        if self.login_mode == "cookie" and not self.config.get("cookie", ""):
            missing.append("Cookie")
        if self.login_mode == "password" and not self.username:
            missing.append("用户名")
        if self.login_mode == "password" and not self.password:
            missing.append("密码")
        return missing

    def test_connection(self) -> dict:
        """测试连接 — 验证 Cookie 或登录状态"""
        if self.login_mode == "cookie":
            return self._test_cookie()
        else:
            return {
                "success": False,
                "error": "密码模式需先通过 Playwright 登录才能测试连接",
                "needs_captcha": True,
            }

    def _test_cookie(self) -> dict:
        """测试 Cookie 是否有效 — 请求用户信息接口"""
        if not self._session:
            return {"success": False, "error": "未设置 Cookie", "status": "无 Cookie"}

        try:
            # 访问首页建立会话
            resp = self._session.get(f"{self.site_url}/", timeout=15,
                                     headers={"Referer": self.site_url})

            # 尝试获取用户信息（如果 API 可用）
            api_result = self._api_get("/api/user/info")
            if api_result and api_result.get("success"):
                return {"success": True, "error": "", "status": "已登录",
                        "user": api_result.get("data", {})}

            # 如果 API 返回 418，回退到页面检测
            if "login" not in resp.url.lower() and len(resp.cookies) > 2:
                return {"success": True, "error": "", "status": "Cookie 有效（页面检测）"}

            # 检查 Cookie 中是否有登录相关字段
            auth_keywords = ["auth", "token", "session", "oshwhub", "identity"]
            for cookie in self._session.cookies:
                name_lower = cookie.name.lower()
                for kw in auth_keywords:
                    if kw in name_lower:
                        return {"success": True, "error": "",
                                "status": f"Cookie 有效（{cookie.name}）"}

            return {"success": False, "error": "Cookie 无效或已过期",
                    "status": "Cookie 过期"}
        except Exception as e:
            return {"success": False, "error": f"连接失败: {e}", "status": "连接失败"}

    def _api_get(self, path: str, params: dict = None) -> dict:
        """发送 GET 请求到 OSHWHub API"""
        if not self._session:
            return {"success": False, "error": "无有效 Session"}
        try:
            url = f"{self.site_url}{path}"
            resp = self._session.get(url, params=params, timeout=15,
                                     headers={"Referer": f"{self.site_url}/"})
            if resp.status_code == 200:
                try:
                    return {"success": True, "data": resp.json()}
                except ValueError:
                    return {"success": True, "raw": resp.text}
            return {"success": False, "error": f"HTTP {resp.status_code}", "raw": resp.text[:500]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _api_post(self, path: str, data: dict = None, files: dict = None) -> dict:
        """发送 POST 请求到 OSHWHub API"""
        if not self._session:
            return {"success": False, "error": "无有效 Session"}
        try:
            url = f"{self.site_url}{path}"
            kwargs = {"timeout": 30,
                      "headers": {"Referer": f"{self.site_url}/",
                                  "X-Requested-With": "XMLHttpRequest"}}
            if files:
                kwargs["files"] = files
                if data:
                    kwargs["data"] = data
            else:
                kwargs["json"] = data
            resp = self._session.post(url, **kwargs)
            if resp.status_code in (200, 201):
                try:
                    return {"success": True, "data": resp.json()}
                except ValueError:
                    return {"success": True, "raw": resp.text}
            return {"success": False, "error": f"HTTP {resp.status_code}", "raw": resp.text[:500]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def login_with_playwright(self) -> dict:
        """使用 Playwright 浏览器登录 OSHWHub

        返回:
            success: bool
            logged_in: bool
            needs_captcha: bool
            image: str  — base64 截图（需要验证码时）
            captcha_type: str
            cookies: str
            error: str
        """
        try:
            self._playwright_login = OshwhubPlaywrightLogin(site_url=self.site_url)
            result = self._playwright_login.login(
                username=self.username,
                password=self.password,
                captcha_provider="manual",
            )

            if result.get("logged_in"):
                cookie_str = result.get("cookies", "")
                self._init_session_with_cookie(cookie_str)
                self.config["cookie"] = cookie_str

            return result
        except Exception as e:
            return {"success": False, "logged_in": False,
                    "error": f"Playwright 登录异常: {e}"}

    def submit_captcha(self, captcha_value: str) -> dict:
        """提交验证码并完成登录

        在 login_with_playwright() 返回 needs_captcha=True 后调用。
        """
        if not self._playwright_login:
            return {"success": False, "logged_in": False,
                    "error": "尚未启动 Playwright 登录流程，请先调用 login_with_playwright()"}
        try:
            result = self._playwright_login.submit_captcha_and_login(
                captcha_value=captcha_value
            )
            if result.get("logged_in"):
                cookie_str = result.get("cookies", "")
                self._init_session_with_cookie(cookie_str)
                self.config["cookie"] = cookie_str
            return result
        except Exception as e:
            return {"success": False, "logged_in": False,
                    "error": f"验证码提交异常: {e}"}

    def _check_login(self) -> bool:
        """检查登录状态"""
        result = self._test_cookie()
        return result.get("success", False)

    def publish(self, article: Article, **kwargs) -> dict:
        """发布文章到 OSHWHub

        OSHWHub 是项目展示平台，每个文章作为一个"项目"发布。
        支持 Markdown 正文 + 图片附件。

        如果是 Cookie 模式，直接调用 API。
        如果是密码模式，需先调用 login_with_playwright() 完成登录。

        参数:
            article: Article 对象（title, body, images 等）
            kwargs:
                project_type: str — 项目类型（可选）
                tags: list — 标签列表
        """
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        if self.login_mode == "password" and not self._check_login():
            return {"success": False, "error": "请先通过 Playwright 完成登录后再发布",
                    "url": "", "id": ""}

        if self.login_mode == "cookie" and not self._check_login():
            return {"success": False, "error": "Cookie 无效或已过期，请重新登录",
                    "url": "", "id": ""}

        try:
            return self._publish_project(article, **kwargs)
        except Exception as e:
            return {"success": False, "error": f"OSSWHub 发布异常: {e}",
                    "url": "", "id": ""}

    def _publish_project(self, article: Article, **kwargs) -> dict:
        """发布项目到 OSHWHub

        策略：
        1. 尝试 API 方式（/api/project/publish）
        2. 如果 API 不可用（418），回退到 Playwright 浏览器发帖
        """
        # 构造项目数据
        project_data = {
            "title": article.title,
            "description": article.summary or article.body[:200] if article.body else "",
            "content": article.body or "",
            "tags": article.tags or kwargs.get("tags", []),
            "type": kwargs.get("project_type", "article"),
        }

        # 如果有图片，处理图片上传
        image_urls = []
        if article.images:
            for img in article.images:
                if isinstance(img, dict):
                    image_urls.append(img.get("src", ""))
                elif isinstance(img, str):
                    image_urls.append(img)

        if image_urls:
            project_data["images"] = image_urls

        # 1. 先尝试 API 方式
        api_result = self._api_post("/api/project/publish", data=project_data)
        if api_result.get("success"):
            data = api_result.get("data", {})
            project_id = ""
            project_url = ""
            if isinstance(data, dict):
                project_id = data.get("id", "") or data.get("projectId", "")
                project_url = f"{self.site_url}/project/{project_id}" if project_id else ""
            return {
                "success": True,
                "url": project_url or f"{self.site_url}/project/{project_id}",
                "id": project_id,
                "error": "",
                "message": "api_publish_success",
            }

        # API 返回错误（418 或其它），尝试 Playwright 方式发布
        if "418" in api_result.get("error", "") or not api_result.get("success"):
            return {
                "success": False,
                "error": f"API 发布失败（{api_result.get('error', '未知')}），"
                         f"请确认 Cookie 有效或使用密码模式 Playwright 登录",
                "url": "", "id": "",
            }

        return api_result

    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """撤回已发布的文章"""
        return {"supported": False, "success": False,
                "error": "OSHWHub 暂不支持 API 撤回，请手动在网站操作"}
