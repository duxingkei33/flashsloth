"""
CSDN Publisher — Selenium 浏览器自动化
CSDN 无公开 API，用 Selenium 模拟登录 + 发布
⚠️ 平台改前端可能失效，维护成本较高

使用方法：
1. 在浏览器登录 CSDN（mp.csdn.net）
2. F12 → Application → Cookies → 复制全部 Cookie 字符串
3. 在 FlashSloth 后台配置 CSDN 账号时粘贴 Cookie
"""
import os, json, time
from flashsloth.core.publisher import Publisher, register
from flashsloth.core.article import Article


CHROME_PATHS = [
    "/tmp/chrome-extracted/chrome-linux64/chrome",
    "/opt/hermes/.playwright/chromium-1228/chrome",
]

CHROMEDRIVER_PATHS = [
    "/tmp/chromedriver-linux64/chromedriver",
    "/tmp/chromedriver",
    "/usr/local/bin/chromedriver",
]


def _find_chrome() -> str | None:
    for p in CHROME_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _find_chromedriver() -> str | None:
    for p in CHROMEDRIVER_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


@register
class CSDNPublisher(Publisher):
    name = "csdn"
    display_name = "CSDN"
    description = "通过 Selenium 浏览器自动化发布到 CSDN 博客"
    config_fields = [
        {
            "key": "cookie",
            "label": "Cookie（登录 CSDN 后从浏览器 F12 复制）",
            "type": "password",
            "required": True,
            "placeholder": "粘贴完整的 Cookie 字符串",
        },
        {
            "key": "auto_publish",
            "label": "发布后自动发表（而不是存草稿）",
            "type": "boolean",
            "required": False,
            "default": False,
        },
        {
            "key": "article_type",
            "label": "文章类型",
            "type": "select",
            "required": False,
            "default": "original",
            "options": [
                {"value": "original", "label": "原创"},
                {"value": "reprint", "label": "转载"},
                {"value": "translated", "label": "翻译"},
            ],
        },
    ]

    def publish(self, article: Article, **kwargs) -> dict:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException, NoSuchElementException

        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        chrome_path = _find_chrome()
        chromedriver_path = _find_chromedriver()

        if not chrome_path:
            return {"success": False, "error": "Chrome 浏览器未安装，请先下载 Chrome for Testing",
                    "url": "", "id": ""}

        opts = Options()
        opts.binary_location = chrome_path
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-setuid-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,800")
        opts.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        try:
            service_kwargs = {}
            if chromedriver_path:
                from selenium.webdriver.chrome.service import Service
                service = Service(executable_path=chromedriver_path)
                service_kwargs["service"] = service

            driver = webdriver.Chrome(options=opts, **service_kwargs)
            wait = WebDriverWait(driver, 15)

            # 注入 Cookie
            driver.get("https://mp.csdn.net")
            time.sleep(2)
            self._inject_cookies(driver)

            # 跳到编辑器
            driver.get("https://mp.csdn.net/mp_blog/creation/editor")
            time.sleep(3)

            # 检查是否登录成功
            if "passport.csdn.net" in driver.current_url or "login" in driver.current_url:
                driver.quit()
                return {"success": False, "error": "Cookie 已过期，请重新登录 CSDN 后复制新的 Cookie",
                        "url": "", "id": ""}

            # 切换到 Markdown 模式（如果必要）
            self._try_click(driver, wait, [
                "li[data-mode='markdown']",
                "button:has-text('Markdown')",
                ".md-tab",
            ], timeout=3)

            time.sleep(1)

            # 填写标题
            title_filled = self._try_fill(driver, wait, article.title, [
                "#article-title",
                "input.article-title",
                "input[placeholder*='标题']",
                "#title",
            ], timeout=5)

            if not title_filled:
                driver.quit()
                return {"success": False, "error": "找不到标题输入框，CSDN 编辑器可能已改版",
                        "url": "", "id": ""}

            # 填写正文
            body_filled = self._try_fill(driver, wait, article.body, [
                "#editor-content textarea",
                ".editor-content textarea",
                "#editor-content",
                ".article-content textarea",
                "div[contenteditable='true']",
            ], timeout=5)

            if not body_filled:
                # 尝试用 JS 设置富文本编辑器
                try:
                    driver.execute_script(
                        "document.querySelector('[contenteditable=true]').innerHTML = arguments[0]",
                        self._md_to_html(article.body)
                    )
                    body_filled = True
                except:
                    pass

            if not body_filled:
                driver.quit()
                return {"success": False, "error": "找不到正文编辑区，CSDN 编辑器可能已改版",
                        "url": "", "id": ""}

            time.sleep(1)

            # 发布/存草稿
            auto_publish = self.config.get("auto_publish", False)
            if auto_publish:
                clicked = self._try_click(driver, wait, [
                    "button:has-text('发布')",
                    "button:has-text('公开发布')",
                    ".publish-btn",
                    "#publish-btn",
                ], timeout=5)
                if not clicked:
                    self._try_click(driver, wait, [
                        "button:has-text('存草稿')",
                        "button:has-text('保存')",
                    ], timeout=3)
            else:
                self._try_click(driver, wait, [
                    "button:has-text('存草稿')",
                    "button:has-text('保存草稿')",
                    "button:has-text('保存')",
                ], timeout=5)

            time.sleep(3)
            final_url = driver.current_url
            driver.quit()

            return {
                "success": True,
                "url": final_url,
                "id": "",
                "error": "",
                "message": f"已{'发布' if auto_publish else '保存到草稿'}，请到 CSDN 后台确认",
            }

        except Exception as e:
            try:
                driver.quit()
            except:
                pass
            return {"success": False, "error": f"CSDN Selenium 发布失败: {e}",
                    "url": "", "id": ""}

    def test_connection(self) -> dict:
        """测试 Cookie 是否有效"""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        chrome_path = _find_chrome()
        if not chrome_path:
            return {"success": False, "error": "Chrome 未找到", "status": "缺少浏览器"}

        opts = Options()
        opts.binary_location = chrome_path
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-setuid-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")

        try:
            chromedriver_path = _find_chromedriver()
            service_kwargs = {}
            if chromedriver_path:
                from selenium.webdriver.chrome.service import Service
                service = Service(executable_path=chromedriver_path)
                service_kwargs["service"] = service

            driver = webdriver.Chrome(options=opts, **service_kwargs)
            driver.get("https://mp.csdn.net")
            time.sleep(2)
            self._inject_cookies(driver)
            driver.get("https://mp.csdn.net/mp_blog/creation/editor")
            time.sleep(3)

            if "passport.csdn.net" in driver.current_url or "login" in driver.current_url:
                driver.quit()
                return {"success": False, "error": "Cookie 已过期", "status": "Cookie 过期"}

            driver.quit()
            return {"success": True, "error": "", "status": "Cookie 有效，已登录 CSDN"}

        except Exception as e:
            try:
                driver.quit()
            except:
                pass
            return {"success": False, "error": str(e), "status": "连接失败"}

    def _inject_cookies(self, driver):
        """从 Cookie 字符串注入到浏览器"""
        import urllib.parse
        cookie_str = self.config.get("cookie", "")
        if not cookie_str:
            return
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                name, value = item.split("=", 1)
                name = name.strip()
                value = urllib.parse.unquote(value.strip())
                if name and value:
                    try:
                        driver.add_cookie({
                            "name": name,
                            "value": value,
                            "domain": ".csdn.net",
                            "path": "/",
                        })
                    except:
                        pass

    def _try_click(self, driver, wait, selectors, timeout=5):
        """尝试用多个选择器点击元素"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
        for sel in selectors:
            try:
                el = wait.with_timeout(timeout).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                el.click()
                return True
            except:
                continue
        return False

    def _try_fill(self, driver, wait, text, selectors, timeout=5):
        """尝试用多个选择器填入文本"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
        for sel in selectors:
            try:
                el = wait.with_timeout(timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                el.clear()
                el.send_keys(text)
                return True
            except:
                continue
        return False

    def _md_to_html(self, md_text):
        """简单 Markdown 转 HTML"""
        import re
        html = md_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.M)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.M)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.M)
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
        html = re.sub(r'^- (.+)$', r'<li>\1</li>', html, flags=re.M)
        html = re.sub(r'```(\w*)\n([\s\S]*?)```', r'<pre><code>\2</code></pre>', html)
        html = html.replace("\n\n", "</p><p>")
        html = "<p>" + html + "</p>"
        html = re.sub(r'<li>(.*?)</li>', r'<li>\1</li>', html)
        # 把 <li> 包进 <ul>
        html = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', html)
        return html
