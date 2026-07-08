"""
得物 Publisher — Playwright 浏览器自动化

得物（dewu.com）是潮流网购社区/电商平台，非内容社区。
- 首页访问即触发阿里云 FeiLin 滑块验证码
- 登录方式：手机号密码/验证码/第三方/扫码
- 无标准内容发布编辑器（editor_url 返回非编辑器页面）
- 此 Publisher 提供登录验证、Cookie 管理，发布操作为占位提示
"""

import re, json, os, logging
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

SITE_URL = "https://www.dewu.com/"
EDITOR_URL = "https://www.dewu.com/editor"
DEWU_DOMAIN = ".dewu.com"


def _parse_cookies(cookie_str: str) -> list:
    """将 Cookie 字符串解析为 Playwright 可接受的格式"""
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        cookies.append({
            "name": n.strip(),
            "value": v.strip(),
            "domain": DEWU_DOMAIN,
            "path": "/",
        })
    return cookies


@register
class DewuPublisher(Publisher):
    name = "dewu"
    display_name = "得物"
    architecture = "自建电商"

    PLATFORM_LIMITS = {
        "dewu.com": {
            "max_title_length": 50,
            "min_title_length": 1,
            "supports_draft": False,
            "supports_schedule": False,
            "supports_cover": False,
            "supports_tags": False,
            "article_types": [],
            "image_upload": "unsupported",
            "note": "得物为电商平台，无内容发布能力",
        }
    }

    login_methods = [
        {"method": "qrcode", "label": "📱 得物APP扫码登录", "icon": "📱", "priority": 1,
         "fields": [],
         "description": "打开得物登录页，使用得物APP扫码登录"},
        {"method": "password", "label": "账号密码登录", "icon": "🔑", "priority": 2,
         "fields": ["username", "password"],
         "description": "输入得物账号和密码，Playwright 浏览器自动登录"},
        {"method": "phone", "label": "手机验证码登录", "icon": "📞", "priority": 3,
         "fields": ["phone"],
         "description": "输入手机号，Playwright 自动发送验证码并等待用户输入"},
        {"method": "oauth", "label": "第三方账号登录（微信/微博/QQ）", "icon": "🔗", "priority": 4,
         "fields": [],
         "description": "支持微信、微博、QQ 第三方账号登录"},
        {"method": "cookie", "label": "Cookie 粘贴（备选）", "icon": "🍪", "priority": 99,
         "fields": ["cookie"],
         "description": "登录后从浏览器 F12 → Application → Cookies → dewu.com 复制"},
    ]
    config_fields = [
        {"key": "username", "label": "手机号/用户名", "type": "text", "required": False, "default": ""},
        {"key": "password", "label": "密码", "type": "password", "required": False, "default": ""},
        {"key": "phone", "label": "手机号", "type": "text", "required": False, "default": ""},
        {"key": "cookie", "label": "Cookie（备选）", "type": "password", "required": False,
         "placeholder": "得物全站 Cookie（从 F12 复制）"},
    ]
    supports_draft = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.logger = logging.getLogger(f"publisher.{self.name}")

    def _cookies(self):
        return _parse_cookies(self.cookie_str) if self.cookie_str else []

    def test_connection(self) -> dict:
        """测试 Cookie 有效性，验证登录态

        得物首页访问可能触发阿里云 FeiLin 滑块验证码，
        测试时需处理验证码干扰。
        """
        if not self.cookie_str:
            return {"success": False, "error": "未配置 Cookie", "status": ""}

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                )
                ctx.add_cookies(self._cookies())
                page = ctx.new_page()

                # 加载首页（注意：首页会触发阿里云滑块验证码）
                page.goto(SITE_URL, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)

                # 检查是否被滑块验证码拦截
                current_url = page.url
                if "captcha" in current_url.lower() or "verify" in current_url.lower():
                    self.logger.info("⚠️ 触发滑块验证码，尝试等待...")
                    page.wait_for_timeout(3000)

                body_text = page.inner_text("body")[:2000]

                # 检测登录态指标
                has_logout = bool(re.search(r"退出|注销", body_text))
                has_user_center = bool(
                    re.search(r"个人中心|我的得物|我的订单|我的收藏|我的足迹", body_text)
                )

                # 提取用户名
                username = self._extract_username(page, body_text)

                # 检测用户头像（强登录标志）
                avatar = page.locator(
                    "[class*='avatar'] img, img[class*='avatar'], "
                    "[class*='user-avatar'], [class*='UserAvatar'], "
                    ".user-info img, [class*='header-user'] img"
                ).first
                has_avatar = avatar.count() > 0

                browser.close()

                # 判定
                strong_login = has_logout or (has_user_center and has_avatar)
                if strong_login and username:
                    return {
                        "success": True,
                        "error": "",
                        "status": f"✅ 已登录 — {username}",
                        "username": username,
                    }
                if strong_login:
                    return {
                        "success": True,
                        "error": "",
                        "status": "✅ 已登录（未识别用户名）",
                    }
                if has_user_center or has_avatar:
                    return {
                        "success": True,
                        "error": "",
                        "status": "✅ 可能已登录",
                    }

                return {
                    "success": False,
                    "error": "Cookie 已过期",
                    "status": "❌ Cookie已失效",
                }

        except Exception as e:
            return {"success": False, "error": str(e), "status": "❌ 连接失败"}

    def _extract_username(self, page, body_text: str) -> str:
        """从页面中提取当前登录用户名"""
        # 尝试常见用户名选择器
        selectors = [
            "[class*='user-name']",
            "[class*='nickname']",
            "[class*='username']",
            "[class*='account']",
            "[class*='header-user'] span",
            "[class*='login-user']",
            "[class*='UserInfo']",
            "[class*='userInfo']",
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.count() > 0:
                    text = el.text_content() or ""
                    text = text.strip()
                    if text and len(text) < 50:
                        return text
            except Exception:
                continue

        # 从头像的 title/alt 属性提取
        try:
            for attr in ["title", "alt"]:
                val = page.locator(
                    "img[class*='avatar'], img[class*='Avatar'], "
                    "[class*='avatar'] img"
                ).first.get_attribute(attr)
                if val and len(val) < 30 and val.strip():
                    return val.strip()
        except Exception:
            pass

        # 正则兜底: 欢迎语或用户名模式
        m = re.search(r"(?:欢迎|你好|Hi)[，,]\s*([^\s，。！!]{1,20})", body_text)
        if m:
            return m.group(1)

        return ""

    def publish(self, article: Article, **kwargs) -> dict:
        """尝试发布到得物（电商平台，无标准内容发布能力）

        得物本质是潮流网购社区，没有博客/文章发布功能。
        此方法会尝试访问 editor_url 确认后返回提示信息。
        save_as_draft 参数保留但实际不执行存草稿。
        """
        result = {
            "success": False,
            "url": "",
            "id": "",
            "error": "",
            "message": "",
        }

        if not self.cookie_str:
            result["error"] = "未配置 Cookie"
            return result

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                )
                ctx.add_cookies(self._cookies())
                page = ctx.new_page()

                try:
                    # 1. 预热首页（可能触发滑块验证码）
                    page.goto(SITE_URL, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)
                    self.logger.info("✅ 首页加载完成")

                    # 检查登录态
                    body_text = page.inner_text("body")[:1000]
                    if not re.search(r"退出|注销|个人中心|我的得物", body_text):
                        raise PublishError("Cookie 已过期，需重新登录")

                    # 2. 尝试访问编辑器 URL 确认其可用性
                    self.logger.info(f"🔍 尝试访问编辑器: {EDITOR_URL}")
                    page.goto(EDITOR_URL, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(3000)

                    current_url = page.url
                    page_title = page.title()

                    self.logger.info(
                        f"编辑器访问结果: URL={current_url[:80]}, Title={page_title[:60]}"
                    )

                    # 检查是否被重定向到首页或登录页（编辑器不存在）
                    if "dewu.com" in current_url and "editor" not in current_url:
                        msg = (
                            "得物是电商平台（潮流网购社区），没有文章/内容发布功能。"
                            f"访问编辑器 URL 后重定向到: {current_url[:50]}"
                        )
                        self.logger.warning(msg)
                        result["error"] = msg
                        result["message"] = "dewu_not_a_content_platform"
                    else:
                        # 编辑器页面存在（罕见情况），保留扩展性
                        self.logger.info("⚠️ 得物编辑器页面存在，但非标准内容编辑器")
                        msg = (
                            "得物为电商平台，无标准内容发布功能。"
                            "如果确实需要在此平台发布，建议使用得物开放平台 API。"
                        )
                        result["error"] = msg
                        result["message"] = "dewu_no_content_publish"

                except PublishError:
                    raise
                except Exception as e:
                    raise PublishError(f"得物发布尝试失败: {str(e)}") from e
                finally:
                    page.close()
                    browser.close()

        except PublishError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)

        return result

    def upload_image(self, local_path: str) -> dict:
        """得物无图床功能"""
        return {
            "success": False,
            "url": "",
            "error": "得物平台无图片上传功能",
        }
