"""
知乎 Publisher — Playwright 浏览器自动化
知乎无公开 API，用 Playwright 模拟发布
⚠️ 平台改前端可能失效，维护成本较高
"""
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register


@register
class ZhihuPublisher(Publisher):
    name = "zhihu"
    display_name = "知乎"
    config_fields = [
        {"key": "cookie", "label": "Cookie", "type": "password", "required": True,
         "placeholder": "登录知乎后从浏览器 F12 复制"},
    ]

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": "缺少配置: Cookie",
                    "url": "", "id": ""}

        # 知乎无公开 API，推荐用 Playwright 方案
        # 使用前需安装: pip install playwright && playwright install chromium
        return {
            "success": False,
            "error": "知乎发布需 Playwright 自动化，请配置后重试。"
                     "或先用 OpenWrite 等第三方服务分发。",
            "url": "", "id": "",
            "setup_guide": "pip install playwright && playwright install chromium",
        }

    def publish_with_playwright(self, article: Article) -> dict:
        """Playwright 方式发布（预留实现）"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"success": False, "error": "请先安装: pip install playwright && playwright install chromium",
                    "url": "", "id": ""}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                # 注入 Cookie
                context.add_cookies([{
                    "name": k.split("=")[0],
                    "value": "=".join(k.split("=")[1:]),
                    "domain": ".zhihu.com",
                    "path": "/",
                } for k in self.config["cookie"].split("; ") if "=" in k])

                page = context.new_page()
                page.goto("https://zhuanlan.zhihu.com/write", timeout=30000)
                page.wait_for_timeout(3000)

                # 填标题
                page.fill("input[placeholder='标题']", article.title)
                # 填正文
                page.fill("div[contenteditable='true']", article.body)
                # 点发布
                page.click("button:has-text('发布')")
                page.wait_for_timeout(5000)

                url = page.url
                browser.close()
                return {"success": True, "url": url, "id": "", "error": ""}

        except Exception as e:
            return {"success": False, "error": f"知乎 Playwright 发布失败: {e}",
                    "url": "", "id": ""}
