"""
OSHWHub Article Publisher — 基于 Playwright (sync) 的立创开源硬件平台文章发布器

目标页面: /article/create  (不是 /project/create)
按钮: "保 存" → 存草稿, "提交审核" → 发布

注意：所有操作必须严格使用 Playwright，禁止 requests/curl/wget。
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


@register
class OSHWHubArticlePublisher(Publisher):
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
    supports_draft = True   # 文章编辑器支持"保 存"存草稿
    supports_cover = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie_str = config.get("cookie", "")
        self.logger = logging.getLogger(f"publisher.{self.name}")

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

        save_as_draft = kwargs.get("save_as_draft", True)
        result = {"success": False, "url": "", "id": "", "error": "", "message": ""}
        _tmp_files = []

        try:
            pw, browser, ctx = self._launch()
            page = ctx.new_page()

            try:
                # ── 1. 导航到文章创建页（不是工程创建页！） ──
                page.goto(f"{BASE}/article/create", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)

                if "login" in page.url.lower() or "passport" in page.url.lower():
                    raise PublishError("Cookie 已过期")

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
                        # 用 file_chooser 触发 Ant Design Upload（用expect_file_chooser不行因为sync API）
                        # 先点击上传区域打开文件选择器
                        upload_area = page.locator(".create_upload__R9JpM, button:has-text('上传图片')").first
                        if upload_area.count() > 0:
                            with page.expect_file_chooser() as fc_info:
                                upload_area.click()
                            fc = fc_info.value
                            fc.set_files(cover_path)
                            page.wait_for_timeout(5000)
                            self.logger.info(f"✅ 封面上传: {os.path.basename(cover_path)}")
                        else:
                            # fallback: 直接set_input_files到隐藏input
                            file_input = page.locator("input[type='file']").first
                            if file_input.count() > 0:
                                file_input.set_input_files(cover_path)
                                page.wait_for_timeout(3000)
                                self.logger.info(f"✅ 封面上传(fallback): {os.path.basename(cover_path)}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ 封面上传失败: {e}")

                # ── 4b. 关掉上传封面后弹出的 ant-modal 遮罩 ──
                try:
                    page.evaluate("""() => {
                        document.querySelectorAll('.ant-modal-close').forEach(b => b.click());
                        document.querySelectorAll('.ant-modal-wrap, .ant-modal-mask').forEach(el => el.remove());
                    }""")
                    page.wait_for_timeout(500)
                except Exception:
                    pass

                # ── 5. 选择分类（OSHWHub分类是radio按钮，非下拉框）──
                try:
                    radio_inputs = page.locator("input[type='radio']")
                    count = radio_inputs.count()
                    if count >= 1:
                        # 选第一个radio（使用技巧/skill），用JS点击绕过遮挡
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
                            // Also trigger ant-design checkbox
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
                    # 先关掉可能残留的modal遮罩
                    page.evaluate("""() => {
                        document.querySelectorAll('.ant-modal-close').forEach(b => b.click());
                        document.querySelectorAll('.ant-modal-wrap, .ant-modal-mask, .ant-modal').forEach(el => el.remove());
                    }""")
                    page.wait_for_timeout(500)
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

                # 等待导航/结果
                page.wait_for_timeout(3000)
                current_url = page.url
                result["url"] = current_url

                # 从 URL 提取文章 ID
                m = re.search(r'/article/([a-zA-Z0-9_]+)', current_url)
                if m:
                    result["id"] = m.group(1)

                result["success"] = True

            except PublishError:
                raise
            except Exception as e:
                raise PublishError(f"OSHWHub 发布失败: {str(e)}") from e
            finally:
                page.close()
                browser.close()
                pw.stop()
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
