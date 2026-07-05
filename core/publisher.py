"""Publisher 基类 + 注册机制"""
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
    config_fields: list[dict] = []     # 配置字段定义

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def publish(self, article: Article, **kwargs) -> dict:
        """
        发布一篇文章
        返回: {"success": bool, "url": str, "id": str, "error": str}
        """
        pass

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
    """列出所有已注册的 Publisher 信息"""
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "config_fields": cls.config_fields,
        }
        for cls in _registry.values()
    ]
