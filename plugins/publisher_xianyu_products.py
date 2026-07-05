"""
闲鱼发布商品 Publisher — 用于发布闲置商品到闲鱼

预留模式：目前闲鱼商品发布 API 尚未完成对接，
需通过 Playwright 浏览器自动化或闲鱼开放平台 API 实现。

注意：闲鱼商品发布与普通文章发布不同，涉及商品图片、
价格、分类、成色等字段。当前版本仅做框架预留。
"""
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class XianyuProductsPublisher(Publisher):
    name = "xianyu_products"
    display_name = "闲鱼发布商品（预留）"
    config_fields = [
        {"key": "username", "label": "淘宝账号", "type": "text", "required": False,
         "placeholder": "用于闲鱼登录的淘宝账号"},
        {"key": "password", "label": "淘宝密码", "type": "password", "required": False,
         "placeholder": "淘宝登录密码"},
        {"key": "cookie", "label": "Cookie", "type": "password", "required": False,
         "placeholder": "登录后从浏览器 F12 复制 Cookie"},
        {"key": "site_url", "label": "平台地址", "type": "text", "required": True,
         "default": "https://goofish.com", "placeholder": "https://goofish.com"},
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        cfg = self.config
        self.username = cfg.get("username", "")
        self.password = cfg.get("password", "")
        self.cookie = cfg.get("cookie", "")

    def publish(self, article: Article, **kwargs) -> dict:
        """
        【预留】发布闲置商品到闲鱼

        当前返回开发中提示。后续实现在插件中接入：
        1. Playwright 浏览器自动化发布
        2. 或闲鱼开放平台 API
        """
        return {
            "success": False,
            "error": "【预留】闲鱼商品发布功能开发中。\n\n"
                     "计划实现方式：\n"
                     "1. 使用 Playwright 模拟浏览器打开闲鱼发布页\n"
                     "2. 自动填写商品标题、描述、价格、分类\n"
                     "3. 上传商品图片\n"
                     "4. 提交发布\n\n"
                     "当前已支持：闲账号登录 + Cookie 保存，欢迎页面可查看。",
        }

    def publish_product(self, title: str, description: str, price: float,
                        images: list[str] = None, category: str = "",
                        condition: str = "全新") -> dict:
        """
        【预留】发布商品专用方法

        Args:
            title: 商品标题
            description: 商品描述
            price: 价格（元）
            images: 图片URL列表
            category: 商品分类
            condition: 成色（全新/二手/闲置）
        """
        return self.publish(Article(title=title, body=description))
