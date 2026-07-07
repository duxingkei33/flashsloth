"""Publisher 基类 + 注册机制 + 登录方法抽象"""
from abc import ABC, abstractmethod
from typing import Optional
from flashsloth.core.article import Article


class PublishError(Exception):
    """发布异常"""
    pass


class Publisher(ABC):
    """所有 Publisher 必须继承此类"""

    name: str = ""                     # 唯一标识，如 "wordpress"
    display_name: str = ""             # 显示名，如 "WordPress"
    architecture: str = ""             # 平台架构类型，如"基于 Discuz! 架构"
    config_fields: list[dict] = []     # 配置字段定义
    login_methods: list[dict] = []     # 支持的登录方法，格式见下方说明

    """
    login_methods 格式：
    [
        {
            "method": "password",     # 唯一标识
            "label": "密码登录",       # 显示名
            "icon": "🔑",             # 图标
            "priority": 1,            # 优先级（1=最高）
            "fields": ["username", "password"],  # 需要的字段
            "description": "使用用户名和密码登录，适合大多数平台",
        },
        {
            "method": "qrcode",
            "label": "二维码扫码登录",
            "icon": "📱",
            "priority": 2,
            "fields": [],
            "description": "打开二维码，用手机扫码登录",
        },
        {
            "method": "phone",
            "label": "手机号码登录",
            "icon": "📞",
            "priority": 3,
            "fields": ["phone"],
            "description": "使用手机号和验证码登录",
        },
        {
            "method": "cookie",
            "label": "Cookie 粘贴",
            "icon": "🍪",
            "priority": 99,
            "fields": ["cookie"],
            "description": "从浏览器 F12 复制 Cookie 粘贴（备选方案）",
        },
    ]
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def publish(self, article: Article, **kwargs) -> dict:
        """
        发布一篇文章
        返回: {"success": bool, "url": str, "id": str, "error": str}
        """
        pass

    def upload_image(self, local_path: str) -> dict:
        """
        上传一张图片到本平台图床。
        
        返回: {"success": bool, "url": str, "error": str}
        
        子类可实现此方法以支持图片上传管线。
        不实现则走 fallback（SM.MS 等第三方图床）。
        """
        return {"success": False, "url": "", "error": "该平台未实现图片上传"}

    def process_images(self, article: Article) -> Article:
        """
        对文章中的所有图片执行上传管线。
        使用 ImagePipeline 统一处理。
        
        返回: 更新过图片 URL 的 Article 对象
        """
        try:
            from core.image_pipeline import ImagePipeline
        except ImportError:
            from flashsloth.core.image_pipeline import ImagePipeline
        
        pipeline = ImagePipeline()
        new_body, images = pipeline.process(
            body=article.body,
            platform_upload_fn=self.upload_image
        )
        article.body = new_body
        return article

    def retract(self, article: Article, publish_log: dict = None) -> dict:
        """
        撤回已发布的文章（可选实现）。
        返回: {"success": bool, "error": str, "message": str}
        """
        return {"success": True, "error": "", "message": "该平台不支持自动撤回，请手动处理"}

    def validate_config(self) -> list[str]:
        """返回缺失的配置项"""
        missing = []
        for field in self.config_fields:
            key = field.get("key")
            required = field.get("required", False)
            if required and not self.config.get(key):
                missing.append(key)
        return missing

    @classmethod
    def get_login_methods(cls) -> list[dict]:
        """获取该平台的登录方法列表（按优先级排序）"""
        return sorted(cls.login_methods, key=lambda m: m.get("priority", 99))


# === 注册中心 ===
_registry: dict[str, type[Publisher]] = {}


def register(cls: type[Publisher]):
    """装饰器：注册 Publisher"""
    _registry[cls.name] = cls
    return cls


def get_publisher(name: str, config: Optional[dict] = None) -> Publisher:
    """工厂方法：获取 Publisher 实例"""
    cls = _registry.get(name)
    if not cls:
        raise KeyError(f"未知 Publisher: {name}，可用: {list(_registry.keys())}")
    return cls(config)


def list_publishers() -> list[dict]:
    """列出所有已注册的 Publisher 信息（含登录方法）"""
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "architecture": getattr(cls, "architecture", ""),
            "config_fields": cls.config_fields,
            "login_methods": cls.get_login_methods(),
        }
        for cls in _registry.values()
    ]


def list_login_methods(platform: str = None) -> list[dict]:
    """列出指定平台或所有平台的登录方法"""
    if platform:
        cls = _registry.get(platform)
        if not cls:
            return []
        return cls.get_login_methods()
    result = {}
    for name, cls in _registry.items():
        methods = cls.get_login_methods()
        if methods:
            result[name] = methods
    return result
