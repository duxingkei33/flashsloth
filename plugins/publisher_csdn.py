"""
CSDN Publisher — Playwright 浏览器自动化
CSDN Markdown 编辑器适配（editor.csdn.net/md/）

使用流程:
  1. Playwright 打开编辑器
  2. 注入 Cookie
  3. 填写标题/正文/分类/标签/类型
  4. 上传图片到 CSDN 图床
  5. 存草稿或发布
"""
import re, json, time, os, random, urllib.parse
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError
try:
    from flashsloth.plugins.browser_session import HumanSession
except ImportError:
    from plugins.browser_session import HumanSession


@register
class CSDNPublisher(Publisher):
    name = "csdn"
    display_name = "CSDN"
    
    PLATFORM_LIMITS = {
        "csdn.net": {
            "max_title_length": 100,
            "min_title_length": 5,
            "supports_draft": True,
            "supports_schedule": True,
            "supports_cover": True,
            "supports_tags": True,
            "article_types": ["original", "reprint", "translated"],
            "image_upload": "api",
        }
    }
    
    login_methods = [
        {"method": "qrcode", "label": "微信扫码登录", "icon": "📱", "priority": 1,
         "fields": [], "description": "打开CSDN微信登录二维码，扫码自动登录"},
        {"method": "sms", "label": "验证码登录", "icon": "📞", "priority": 2,
         "fields": ["phone"], "description": "手机号+短信验证码登录"},
        {"method": "app_qrcode", "label": "APP扫码登录", "icon": "📲", "priority": 3,
         "fields": [], "description": "CSDN APP扫码登录"},
        {"method": "cookie", "label": "Cookie 粘贴", "icon": "🍪", "priority": 99,
         "fields": ["cookie"], "description": "从浏览器 F12 复制 Cookie 粘贴"},
    ]
    
    config_fields = [
        {"key": "login_mode", "label": "登录方式", "type": "select", "required": True,
         "options": [
             {"value": "qrcode", "label": "微信扫码登录"},
             {"value": "cookie", "label": "Cookie粘贴"},
         ], "placeholder": "选择登录方式"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": False,
         "placeholder": "CSDN 全站 Cookie"},
        {"key": "article_type", "label": "默认文章类型", "type": "select", "required": False,
         "default": "original",
         "options": [
             {"value": "original", "label": "原创"},
             {"value": "reprint", "label": "转载"},
             {"value": "translated", "label": "翻译"},
         ]},
        {"key": "category", "label": "默认分类", "type": "text", "required": False,
         "placeholder": "分类名称（可选）"},
        {"key": "tags", "label": "默认标签", "type": "text", "required": False,
         "placeholder": "逗号分隔的标签（可选）"},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.cookie = config.get("cookie", "")
        self.site_url = "https://www.csdn.net"
        self.editor_url = "https://editor.csdn.net/md/"
        self.article_type = config.get("article_type", "original")
        self.supports_draft = True
        
        # 使用 HumanSession 管理浏览器
        self.browser = HumanSession(base_url=self.editor_url, min_delay=0.5, max_delay=2.0)
        if self.cookie:
            self.browser.set_cookies(self.cookie)

    def validate_config(self) -> list[str]:
        missing = []
        if not self.cookie:
            missing.append("Cookie")
        return missing

    def test_connection(self) -> dict:
        """测试 CSDN Cookie 是否有效"""
        try:
            resp = self.browser.get("https://blog.csdn.net")
            if "passport.csdn.net" in resp.url or "login" in resp.url.lower():
                return {"success": False, "error": "Cookie 已过期", "status": "Cookie过期"}
            if "duxingkei" in resp.text or "blog.csdn.net" in resp.url:
                return {"success": True, "error": "", "status": "已登录"}
            return {"success": True, "error": "", "status": "Cookie 有效"}
        except Exception as e:
            return {"success": False, "error": f"连接失败: {e}", "status": "连接失败"}

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}
        
        save_as_draft = kwargs.get("save_as_draft", True)
        category = kwargs.get("category", self.config.get("category", ""))
        tags = kwargs.get("tags", self.config.get("tags", ""))
        article_type = kwargs.get("article_type", self.article_type)
        
        try:
            result = self._publish_article(
                article, save_as_draft=save_as_draft,
                category=category, tags=tags, article_type=article_type
            )
            return result
        except Exception as e:
            return {"success": False, "error": f"CSDN 发布异常: {e}",
                    "url": "", "id": ""}

    def _publish_article(self, article: Article, save_as_draft: bool = True,
                         category: str = "", tags: str = "",
                         article_type: str = "original") -> dict:
        """使用 Playwright 发布文章到 CSDN"""
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            
            # 注入 Cookie
            for pair in self.cookie.split(';'):
                pair = pair.strip()
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    try:
                        ctx.add_cookies([{
                            'name': name.strip(),
                            'value': urllib.parse.unquote(value.strip()),
                            'domain': '.csdn.net',
                            'path': '/',
                        }])
                    except:
                        pass
            
            page = ctx.new_page()
            
            # Step 1: 验证登录
            page.goto("https://passport.csdn.net/v1/api/check/userstatus")
            page.wait_for_load_state("networkidle")
            
            # Step 2: 打开编辑器
            page.goto(self.editor_url)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            
            # 检查是否被重定向到登录页
            if "passport.csdn.net" in page.url:
                browser.close()
                return {"success": False, "error": "Cookie 已过期，请重新登录",
                        "url": "", "id": ""}
            
            # Step 3: 填写标题
            title_input = page.locator("input[placeholder*='标题']").first
            if title_input.count() > 0:
                title_input.fill(article.title[:100])
                print(f"  ✅ 标题已填写: {article.title[:50]}...")
            else:
                browser.close()
                return {"success": False, "error": "找不到标题输入框",
                        "url": "", "id": ""}
            
            # Step 4: 填写正文
            # CSDN Markdown 编辑器 - 正文区域是 contenteditable div 或 textarea
            body_area = page.locator("#editor-content, .editor-content, div[contenteditable='true'], textarea").first
            if body_area.count() > 0:
                body_text = article.body or ""
                # CSDN 的 Markdown 编辑器接受直接输入
                try:
                    body_area.fill(body_text)
                    print(f"  ✅ 正文已填写 ({len(body_text)} chars)")
                except:
                    # 使用 JS 设置
                    page.evaluate(f"document.querySelector('[contenteditable=true]').innerText = arguments[0]", body_text)
                    print(f"  ✅ 正文已通过JS填写 ({len(body_text)} chars)")
            else:
                print("  ⚠️ 未找到正文编辑区")
            
            # Step 5: 选择文章类型（如果可用）
            if article_type:
                type_selectors = [
                    f"text={article_type}",
                    f"[data-type='{article_type}']",
                    f"label:has-text('{article_type}')",
                ]
                for sel in type_selectors:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click()
                        print(f"  ✅ 文章类型已选择: {article_type}")
                        page.wait_for_timeout(500)
                        break
            
            # Step 6: 设置标签
            if tags:
                tag_input = page.locator("input[placeholder*='标签'], input[placeholder*='tag']").first
                if tag_input.count() > 0:
                    tag_input.fill(tags)
                    print(f"  ✅ 标签已填写: {tags}")
            
            # Step 7: 设置分类
            if category:
                cat_selectors = [
                    f"text={category}",
                    f"[data-category='{category}']",
                ]
                for sel in cat_selectors:
                    el = page.locator(sel).first
                    if el.count() > 0 and el.is_visible():
                        el.click()
                        print(f"  ✅ 分类已选择: {category}")
                        break
            
            # Step 8: 处理图片上传
            image_warnings = []
            if article.body:
                images = re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', article.body)
                for alt, src in images:
                    if src.startswith("/static/"):
                        local_path = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            src.lstrip("/")
                        )
                        if os.path.isfile(local_path):
                            # 通过 CSDN 上传 API 上传图片
                            try:
                                csdn_url = self._upload_to_csdn(page, local_path)
                                if csdn_url:
                                    # 替换正文中的图片引用
                                    article.body = article.body.replace(src, csdn_url)
                                    print(f"  ✅ 图片已上传: {csdn_url}")
                                else:
                                    image_warnings.append(f"图片上传失败: {src}")
                            except Exception as e:
                                image_warnings.append(f"图片上传异常: {src} -> {str(e)[:60]}")
            
            # Step 9: 保存/发布
            if save_as_draft:
                # 找存草稿按钮
                draft_btn_selectors = [
                    "button:has-text('存草稿')",
                    "button:has-text('保存草稿')",
                    "button:has-text('保存')",
                ]
                clicked = False
                for sel in draft_btn_selectors:
                    btn = page.locator(sel).first
                    if btn.count() > 0 and btn.is_visible():
                        # 关闭可能的遮罩
                        page.evaluate("document.querySelector('.modal')?.remove()")
                        page.wait_for_timeout(500)
                        btn.click()
                        clicked = True
                        print(f"  ✅ 已点击存草稿")
                        break
                
                if not clicked:
                    print("  ⚠️ 未找到存草稿按钮")
            else:
                # 直接发布
                publish_btn = page.locator("button:has-text('发布文章'), button:has-text('发布')").first
                if publish_btn.count() > 0:
                    # 关闭可能的遮罩
                    page.evaluate("document.querySelector('.modal')?.remove()")
                    page.wait_for_timeout(500)
                    publish_btn.click()
                    print(f"  ✅ 已点击发布文章")
                else:
                    print("  ⚠️ 未找到发布按钮")
            
            page.wait_for_timeout(5000)
            
            final_url = page.url
            page.screenshot(path="/tmp/csdn_publish_result.png")
            
            # 检查结果
            result_html = page.content()
            result_url = ""
            article_id = ""
            
            # 尝试从跳转URL获取文章ID
            url_match = re.search(r'article/details/(\d+)', final_url)
            if url_match:
                article_id = url_match.group(1)
                result_url = f"https://blog.csdn.net/duxingkei/article/details/{article_id}"
            
            # 尝试从页面内容获取
            if not result_url:
                detail_match = re.search(r'article/details/(\d+)', result_html)
                if detail_match:
                    article_id = detail_match.group(1)
                    result_url = f"https://blog.csdn.net/duxingkei/article/details/{article_id}"
            
            message = "draft" if save_as_draft else "published"
            
            browser.close()
            
            return {
                "success": True,
                "url": result_url,
                "id": article_id,
                "error": "",
                "message": message,
                "warnings": image_warnings,
            }

    def _upload_to_csdn(self, page, local_path: str) -> str:
        """上传图片到 CSDN 图床"""
        import requests as req
        
        # 从页面获取上传 token/参数
        # CSDN 上传 API: https://bizapi.csdn.net/blog/phoenix/console/v1/upload
        upload_api = "https://bizapi.csdn.net/blog/phoenix/console/v1/file/upload"
        
        # 从 cookie 中提取认证头
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*",
        }
        
        with open(local_path, "rb") as f:
            files = {
                "file": (os.path.basename(local_path), f, "image/png"),
            }
            try:
                resp = req.post(upload_api, headers=headers, files=files, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == 200:
                        return data["data"]["url"]
                    elif data.get("url"):
                        return data["url"]
                    elif data.get("data"):
                        return data["data"]
            except:
                pass
        
        # 备用：通过 Playwright 上传
        try:
            # 找文件上传input
            file_input = page.locator("input[type='file']").first
            if file_input.count() > 0:
                file_input.set_input_files(local_path)
                page.wait_for_timeout(3000)
                # 等待上传完成 - 检查页面中出现的图片URL
                html = page.content()
                img_urls = re.findall(r'https://img-blog\.csdnimg\.cn/[^\s\"<>]+', html)
                if img_urls:
                    return img_urls[0]
        except:
            pass
        
        return ""

    def upload_image(self, local_path: str) -> dict:
        """上传图片到 CSDN 图床"""
        url = self._upload_to_csdn(None, local_path)
        if url:
            return {"success": True, "url": url, "error": ""}
        return {"success": False, "url": "", "error": "上传失败"}
