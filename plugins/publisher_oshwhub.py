"""
OSHWHub Article Publisher — 基于 Playwright (sync) 的立创开源硬件平台文章发布器

目标页面: /article/create  (不是 /project/create)
按钮: "保 存" → 存草稿, "提交审核" → 发布

注意：使用即时登录上下文（OshwhubPlaywrightLogin）而非 cookie 字符串重建，
因为 oshwhub.com 使用 JLC 统一登录（passport.jlc.com），cookie 字符串丢失
domain/path 信息（特别是多个 JSESSIONID 不同路径），导致 SSO 无法正常工作。
"""
import re, json, os, tempfile, logging
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

BASE = "https://oshwhub.com"
logger = logging.getLogger(__name__)


def _ensure_cover_image(article: Article) -> str | None:
    if article.cover and os.path.isfile(str(article.cover)):
        return str(article.cover)
    if article.assets:
        for a in article.assets:
            if os.path.isfile(str(a)):
                return str(a)
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img = Image.new("RGB", (800, 600), color=(52, 152, 219))
    draw = ImageDraw.Draw(img)
    draw.text((400, 300), "Cover", fill="white", anchor="mm")
    img.save(tmp.name)
    return tmp.name


def _fresh_login_context(username: str, password: str) -> tuple:
    """
    Get a fresh Playwright context logged into oshwhub.com.
    Uses OshwhubPlaywrightLogin for proper JLC SSO login.
    
    Returns: (pw, browser, ctx, page) — caller MUST clean up.
    Raises PublishError on failure.
    """
    from plugins.oshwhub_login import OshwhubPlaywrightLogin
    login = OshwhubPlaywrightLogin(site_url=BASE)
    result = login.login(username, password, captcha_provider="manual")
    if not result.get("logged_in"):
        login.close()
        raise PublishError(f"OSHWHub 登录失败: {result.get('error', '未知错误')}")
    
    # Return the login's browser components directly
    # Note: login.page, login.context, login.browser, login._pw are available
    pw = getattr(login, '_pw', None)
    browser = login.browser
    ctx = login.context
    page = login.page
    
    # Navigate to main page to ensure all cookies are established
    page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
    page.wait_for_timeout(3000)
    
    # Save fresh cookies back to DB for future use (not required for this flow)
    _save_cookies_to_db(ctx, username)
    
    return pw, browser, ctx, page, login


def _save_cookies_to_db(ctx, username_hint: str = ""):
    """
    Save ALL browser context cookies as JSON array to the DB.
    This preserves domain/path/secure info unlike flat cookie strings.
    """
    try:
        import sqlite3
        cookies = ctx.cookies()
        # Playwright returns cookies as list of dicts with name, value, domain, path, etc.
        # Convert to JSON-safe dicts
        safe_cookies = []
        for c in cookies:
            safe_c = {}
            for k in ("name", "value", "domain", "path", "httpOnly", "secure", "sameSite", "expires"):
                if k in c:
                    safe_c[k] = c[k]
            safe_cookies.append(safe_c)
        cookie_json = json.dumps(safe_cookies, ensure_ascii=False)
        
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id, config_json FROM platform_accounts WHERE platform='oshwhub'").fetchone()
        if row:
            cfg = json.loads(row["config_json"])
            cfg["cookies_json"] = cookie_json
            # Also update the flat cookie string for backward compatibility
            flat_parts = []
            for c in safe_cookies:
                flat_parts.append(f"{c['name']}={c['value']}")
            cfg["cookie"] = "; ".join(flat_parts)
            conn.execute("UPDATE platform_accounts SET config_json=? WHERE platform='oshwhub'", (json.dumps(cfg),))
            conn.commit()
            logger.info(f"✅ Fresh cookies saved to DB ({len(safe_cookies)} cookies)")
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ 保存 cookie 到 DB 失败: {e}")


# ─────────────────────────────────────────────────────────
# 数据驱动：从探索JSON读取登录状态验证条件（铁律#19）
# ─────────────────────────────────────────────────────────
def _load_login_indicators() -> dict:
    """从探索JSON加载 login_indicator_selectors（数据驱动，不硬编码）"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report_path = os.path.join(base_dir, "platform_reports",
                               "oshwhub_exploration_report.json")
    if not os.path.exists(report_path):
        logger.warning("⚠️ 探索报告不存在，回退默认严格判断")
        return {}
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("login_indicator_selectors", {})
    except Exception as e:
        logger.warning(f"⚠️ 加载探索报告失败: {e}")
        return {}


def _check_login_indicators(page) -> dict:
    """根据探索JSON的 indicators 检查登录状态（数据驱动，铁律#19）

    读取 required_indicators_for_success 和 optional_indicators，
    动态判断 logged_in。若探索数据未配，回退到严格逻辑
    (avatar + (username or exit/logout))。

    Returns: {"logged_in": bool, "detail": str, "username_text": str}
    """
    ind = _load_login_indicators()
    required = ind.get("required_indicators_for_success", [])
    optional = ind.get("optional_indicators", [])
    avatar_sel = ind.get("avatar", "[class*='user-avatar']")
    username_sels = ind.get("username_display", [
        "[class*='user-name']", "[class*='nickname']", "[class*='username']",
        "[class*='display-name']", "[class*='profile-name']",
    ])
    logout_texts = ind.get("logout_text", ["退出", "注销"])

    # Check avatar
    has_avatar = page.locator(avatar_sel).first.count() > 0

    # Check username / display-name
    has_username = False
    username_text = ""
    if username_sels:
        uname_el = page.locator(", ".join(username_sels)).first
        has_username = uname_el.count() > 0
        username_text = (uname_el.text_content() or "").strip() if has_username else ""

    # Check exit/logout text
    has_exit_or_logout = False
    if logout_texts:
        sel_parts = []
        for t in logout_texts:
            sel_parts.append(f"a:has-text('{t}')")
            sel_parts.append(f"button:has-text('{t}')")
            sel_parts.append(f"span:has-text('{t}')")
        has_exit_or_logout = page.locator(", ".join(sel_parts)).first.count() > 0

    # Data-driven: if exploration report has required_indicators, use it strictly
    if required:
        indicator_map = {"avatar": has_avatar, "退出": has_exit_or_logout, "用户名": has_username}
        logged_in = all(indicator_map.get(r, False) for r in required)
    else:
        # Fallback: old strict logic (avatar + (username or exit/logout))
        logged_in = has_avatar and (has_username or has_exit_or_logout)

    if logged_in:
        detail = f"已登录（{username_text}）" if username_text else "已登录"
    else:
        detail = "登录失败"

    return {"logged_in": logged_in, "detail": detail, "username_text": username_text}


@register
class OSHWHubArticlePublisher(Publisher):
    name = "oshwhub"
    display_name = "立创开源硬件平台"
    architecture = "立创开源硬件平台"
    login_methods = [
        {"method": "qrcode", "label": "📱 扫码登录", "icon": "📱", "priority": 1,
         "fields": ["site_url"],
         "description": "打开 OSHWHub 登录页截图，用手机扫码访问后自动捕获 Cookie"},
        {"method": "password", "label": "账号密码登录", "icon": "🔑", "priority": 2,
         "fields": ["site_url", "username", "password"],
         "description": "输入邮箱/手机号和密码，Playwright 浏览器自动登录"},
        {"method": "phone", "label": "手机验证码登录", "icon": "📞", "priority": 3,
         "fields": ["site_url", "phone"],
         "description": "输入手机号，Playwright 自动发送验证码并等待用户输入"},
        {"method": "cookie", "label": "Cookie 粘贴（备选）", "icon": "🍪", "priority": 99,
         "fields": ["cookie"],
         "description": "从浏览器 F12 → Application → Cookies → oshwhub.com 复制"},
    ]
    config_fields = [
        {"key": "cookie", "label": "Cookie（完整 Cookie 字符串）", "type": "password", "required": True,
         "placeholder": "登录后从浏览器复制 Cookie"},
        {"key": "username", "label": "账号（邮箱/手机号）", "type": "text", "required": True, "default": ""},
        {"key": "password", "label": "密码", "type": "password", "required": True, "default": ""},
    ]
    supports_draft = True   # 文章编辑器支持"保 存"存草稿
    supports_cover = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self.logger = logging.getLogger(f"publisher.{self.name}")

    def test_connection(self) -> dict:
        if not self.cookie_str and not (self.username and self.password):
            return {"success": False, "error": "未配置 Cookie 或账号密码"}
        if self.username and self.password:
            try:
                pw, browser, ctx, page, login = _fresh_login_context(self.username, self.password)
                check = _check_login_indicators(page)
                browser.close()
                pw.stop()
                ok = check["logged_in"]
                return {"success": ok, "error": "" if ok else "登录失败", "status": check["detail"]}
            except Exception as e:
                return {"success": False, "error": str(e)}
        else:
            # Fallback: use flat cookie string (may fail for article/create)
            try:
                pw = sync_playwright().start()
                browser = pw.chromium.launch(headless=True, args=[
                    '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
                ])
                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    viewport={"width": 1920, "height": 1080}, locale="zh-CN",
                )
                ctx.add_cookies(self._parse_cookies_fallback(self.cookie_str))
                page = ctx.new_page()
                page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(3000)
                check = _check_login_indicators(page)
                browser.close()
                pw.stop()
                ok = check["logged_in"]
                return {"success": ok, "error": "" if ok else "Cookie 过期", "status": check["detail"] if ok else "Cookie 过期或未登录"}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def _parse_cookies_fallback(self, cookie_str: str) -> list:
        """Fallback cookie parser for backward compatibility (loses domain info)."""
        cookies = []
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            n, v = pair.split("=", 1)
            cookies.append({"name": n.strip(), "value": v.strip(), "domain": ".oshwhub.com", "path": "/"})
        return cookies

    def publish(self, article: Article, **kwargs) -> dict:
        save_as_draft = kwargs.get("save_as_draft", True)
        result = {"success": False, "url": "", "id": "", "error": "", "message": ""}
        _tmp_files = []
        login = None

        try:
            # ── 0. 获取即时登录上下文 ──
            pw, browser, ctx, page, login = _fresh_login_context(self.username, self.password)

            try:
                # ── 1. 导航到文章创建页（不是工程创建页！） ──
                page.goto(f"{BASE}/article/create", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)

                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise PublishError("Cookie 已过期或 SSO 授权失败")

                # ── 2. 文章标题 ──
                title_input = page.locator("#title").first
                if title_input.count() == 0:
                    raise PublishError("找不到文章标题输入框")
                title_input.fill(article.title[:100])
                self.logger.info(f"✅ 文章标题: {article.title[:30]}...")

                # ── 3. 文章简介 ──
                intro = (article.summary or article.content or "")[:100]
                if intro:
                    intro_input = page.locator("#introduction").first
                    if intro_input.count() > 0:
                        intro_input.fill(intro)
                        self.logger.info("✅ 文章简介已填写")

                # ── 4. 封面上传 ──
                cover_path = _ensure_cover_image(article)
                if cover_path:
                    _tmp_files.append(cover_path)
                    try:
                        file_input = page.locator("input[type='file']").first
                        if file_input.count() > 0:
                            file_input.set_input_files(cover_path)
                            page.wait_for_timeout(3000)
                            self.logger.info(f"✅ 封面上传: {os.path.basename(cover_path)}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ 封面上传失败: {e}")

                # ── 4b. 关掉上传封面后弹出的 ant-modal 遮罩 ──
                # 使用 Escape 键触发 Ant Design 原生关闭事件（dispatchEvent + DOM remove 无法触发 React 状态）
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(800)
                except Exception:
                    pass
                # 如果 Escape 没生效，再尝试点击关闭按钮
                try:
                    close_btn = page.locator('.ant-modal-close').first
                    if close_btn.count() > 0 and close_btn.is_visible():
                        close_btn.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

                # ── 5. 选择分类（OSHWHub分类是radio按钮，非下拉框）──
                try:
                    radio_inputs = page.locator("input[type='radio']")
                    count = radio_inputs.count()
                    if count >= 1:
                        first_radio = radio_inputs.first
                        first_radio.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('change', {bubbles: true})); }")
                        page.wait_for_timeout(500)
                        self.logger.info(f"✅ 已选择分类（radio #{1}/{count}）")
                except Exception as e:
                    self.logger.warning(f"⚠️ 分类选择失败: {e}")

                # ── 6. 正文（TinyMCE） ──
                body = article.body or article.content or ""
                if body:
                    page.wait_for_selector(".tox-tinymce", timeout=10000)
                    page.evaluate(f"""
                        (() => {{
                            const editor = tinymce?.activeEditor;
                            if (editor) {{
                                editor.setContent({json.dumps(body)});
                            }}
                        }})()
                    """)
                    self.logger.info(f"✅ 正文已填写 ({len(body)} chars)")

                # ── 7. 勾选协议（用 JS 绕过遮挡） ──
                try:
                    page.evaluate("""
                        const cb = document.querySelector('#is_permit');
                        if (cb) {
                            cb.checked = true;
                            cb.dispatchEvent(new Event('change', {bubbles: true}));
                            const antCb = cb.closest('.ant-checkbox');
                            if (antCb) antCb.classList.add('ant-checkbox-checked');
                        }
                    """)
                    page.wait_for_timeout(300)
                    self.logger.info("✅ 已勾选发布协议")
                except Exception as e:
                    self.logger.warning(f"⚠️ 勾选协议失败: {e}")

                # ── 8. 点击保 存（存草稿）或提交审核（发布）(force=True) ──
                if save_as_draft:
                    # 关闭可能残留的 modal（Escape 键比 DOM remove 更可靠）
                    try:
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(500)
                    except Exception:
                        pass
                    try:
                        close_btn = page.locator('.ant-modal-close').first
                        if close_btn.count() > 0 and close_btn.is_visible():
                            close_btn.click()
                            page.wait_for_timeout(300)
                    except Exception:
                        pass
                    save_btn = page.locator("button:has-text('保 存')").first
                    if save_btn.count() > 0:
                        save_btn.click(force=True)
                        page.wait_for_timeout(5000)
                        self.logger.info("✅ 已点击「保 存」存草稿")
                        result["message"] = "draft_saved"
                    else:
                        raise PublishError("找不到「保 存」按钮")
                else:
                    publish_btn = page.locator("button:has-text('提交审核')").first
                    if publish_btn.count() > 0:
                        publish_btn.click(force=True)
                        page.wait_for_timeout(8000)
                        self.logger.info("✅ 已点击「提交审核」发布")
                        result["message"] = "published"
                    else:
                        raise PublishError("找不到「提交审核」按钮")

                page.wait_for_timeout(3000)
                current_url = page.url
                result["url"] = current_url

                m = re.search(r'/article/([a-zA-Z0-9_]+)', current_url)
                if m:
                    result["id"] = m.group(1)

                result["success"] = True

            except PublishError:
                raise
            except Exception as e:
                raise PublishError(f"OSHWHub 发布失败: {str(e)}") from e
            finally:
                for f in _tmp_files:
                    try:
                        if f and os.path.exists(f) and 'tmp' in f:
                            os.unlink(f)
                    except Exception:
                        pass

        except PublishError as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)
        finally:
            if login:
                try:
                    login.close()
                except Exception:
                    pass
            elif pw and browser:
                try:
                    browser.close()
                    pw.stop()
                except Exception:
                    pass

        return result
