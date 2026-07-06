"""
OSHWHub Publisher — 基于 Playwright (sync) 的立创开源硬件平台发布器

注意：立创开源硬件平台 (oshwhub.com) 创建工程时没有"存草稿"功能，
只有"创 建"按钮会直接发布工程。所以 supports_draft 设为 False。

页面必填项：
  - 标题 #name
  - 封面（图片上传）
  - 开源协议 #license
  - 正文（TinyMCE）
"""
import re, json, os, tempfile, logging
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
from playwright.sync_api import sync_playwright

BASE = "https://oshwhub.com"
logger = logging.getLogger(__name__)


def _parse_cookies(cookie_str: str) -> list:
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        cookies.append({"name": n.strip(), "value": v.strip(), "domain": ".oshwhub.com", "path": "/"})
    return cookies


def _ensure_cover_image(article: Article) -> str | None:
    """如果有封面/附件直接用，否则生成一个临时占位封面"""
    if article.cover and os.path.isfile(str(article.cover)):
        return str(article.cover)
    if article.assets:
        for a in article.assets:
            if os.path.isfile(str(a)):
                return str(a)
    # 生成临时占位封面
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        logger.warning("PIL not available, skip cover generation")
        return None

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img = Image.new("RGB", (800, 600), color=(52, 152, 219))
    draw = ImageDraw.Draw(img)
    draw.text((400, 300), "Cover", fill="white", anchor="mm")
    img.save(tmp.name)
    logger.info(f"✅ 已生成临时封面: {tmp.name}")
    return tmp.name


@register
class OSHWHubPublisher(Publisher):
    name = "oshwhub"
    display_name = "立创开源硬件平台"
    login_methods = [
        {"method": "cookie", "label": "Cookie 粘贴", "icon": "🍪", "priority": 1,
         "fields": ["cookie"],
         "description": "从浏览器 F12 → Application → Cookies → oshwhub.com 复制"},
    ]
    config_fields = [
        {"key": "cookie", "label": "Cookie（完整 Cookie 字符串）", "type": "password", "required": True,
         "placeholder": "登录后从浏览器复制 Cookie"},
    ]
    supports_draft = False  # oshwhub 没有存草稿功能，创建即发布
    supports_cover = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")

    def _cookies(self):
        return _parse_cookies(self.cookie_str) if self.cookie_str else []

    def _launch(self):
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage',
        ])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1920, "height": 1080}, locale="zh-CN",
        )
        ctx.add_cookies(self._cookies())
        return pw, browser, ctx

    def test_connection(self) -> dict:
        if not self.cookie_str:
            return {"success": False, "error": "未配置 Cookie"}
        try:
            pw, browser, ctx = self._launch()
            page = ctx.new_page()
            page.goto(f"{BASE}/", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            avatar = page.locator("[class*='user-avatar']").first
            login_links = page.locator("a:has-text('登录')")
            ok = avatar.count() > 0 or login_links.count() == 0
            browser.close()
            pw.stop()
            return {"success": ok, "error": "" if ok else "Cookie 过期", "status": "已登录" if ok else "Cookie过期"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def publish(self, article: Article, **kwargs) -> dict:
        if not self.cookie_str:
            return {"success": False, "error": "未配置 Cookie", "url": "", "id": ""}

        result = {"success": False, "url": "", "id": "", "error": "", "message": ""}
        _tmp_files = []

        try:
            pw, browser, ctx = self._launch()
            page = ctx.new_page()

            try:
                # ── 1. 导航到创建页 ──
                page.goto(f"{BASE}/project/create", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)

                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise PublishError("Cookie 已过期")

                # ── 2. 工程名称 ──
                name_input = page.locator("#name").first
                if name_input.count() == 0:
                    raise PublishError("找不到工程名称输入框")
                name_input.fill(article.title[:50])
                self.logger.info(f"✅ 工程名称: {article.title[:30]}...")

                # ── 3. 工程简介 ──
                intro = (article.summary or "")[:100]
                if not intro and article.content:
                    intro = article.content[:100]
                if intro:
                    intro_input = page.locator("#introduction").first
                    if intro_input.count() > 0:
                        intro_input.fill(intro)
                        self.logger.info("✅ 工程简介已填写")

                # ── 4. 封面上传（必填） ──
                cover_path = _ensure_cover_image(article)
                if cover_path:
                    _tmp_files.append(cover_path)  # track for cleanup
                    try:
                        # oshwhub 封面上传通过 input[type=file] 实现
                        file_input = page.locator("input[type='file']").first
                        if file_input.count() > 0:
                            file_input.set_input_files(cover_path)
                            page.wait_for_timeout(3000)
                            self.logger.info(f"✅ 封面上传: {os.path.basename(cover_path)}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ 封面上传失败: {e}")

                # ── 5. 选择开源协议（必填） ──
                try:
                    license_sel = page.locator("#license").first
                    if license_sel.count() > 0:
                        license_sel.click()
                        page.wait_for_timeout(1000)
                        # 选第一个可用协议 (Apache 2.0)
                        option = page.locator("[class*='ant-select-item-option']:has-text('Apache')").first
                        if option.count() == 0:
                            option = page.locator("[class*='ant-select-item-option']").nth(1)
                        if option.count() > 0:
                            option.click()
                            page.wait_for_timeout(500)
                            self.logger.info("✅ 已选择开源协议: Apache 2.0")
                except Exception as e:
                    self.logger.warning(f"⚠️ 协议选择失败: {e}")

                # ── 6. TinyMCE 正文 ──
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

                # ── 7. 点击创 建 ──
                create_btn = page.locator("button:has-text('创 建')").first
                if create_btn.count() == 0:
                    raise PublishError("找不到「创 建」按钮")
                create_btn.click()
                self.logger.info("⏳ 等待发布完成...")

                # 等待导航
                page.wait_for_timeout(8000)
                try:
                    page.wait_for_url("**/project/**", timeout=20000)
                except Exception:
                    pass
                page.wait_for_timeout(3000)

                current_url = page.url
                result["url"] = current_url

                # 从 URL 提取 project ID
                m = re.search(r'/project/([a-zA-Z0-9]+)', current_url)
                if m:
                    result["id"] = m.group(1)
                    result["message"] = "published"
                    result["success"] = True
                    self.logger.info(f"✅ 发布成功! URL: {current_url}")
                else:
                    # 检查是否跳转到了新页面
                    if current_url != f"{BASE}/project/create":
                        result["message"] = "published"
                        result["success"] = True
                    else:
                        # 可能仍停留在创建页，检查是否有错误提示
                        errors = page.query_selector_all(".ant-form-item-explain, .ant-message-notice")
                        err_texts = [e.inner_text().strip() for e in errors if e.is_visible()]
                        err_msg = "; ".join(err_texts[:3])
                        if err_msg:
                            raise PublishError(f"表单验证失败: {err_msg}")
                        raise PublishError("发布失败，页面未跳转")

            except PublishError:
                raise
            except Exception as e:
                raise PublishError(f"OSHWHub 发布失败: {str(e)}") from e
            finally:
                page.close()
                browser.close()
                pw.stop()
                # 清理临时文件
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

        return result
