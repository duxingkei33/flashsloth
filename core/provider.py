"""Provider 抽象基类 — 统一内容来源接口

所有 Provider（Markdown、Notion、淘宝、B站等）必须继承此类。
复用 core/publisher.py 相同的注册模式。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContentItem:
    """统一内容项数据模型"""
    id: str
    title: str
    summary: str = ""
    source: str = ""          # 平台来源标识
    url: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    raw_data: dict = field(default_factory=dict)


class Provider(ABC):
    """所有内容来源 Provider 必须继承此类"""

    name: str = ""             # 唯一标识 "markdown", "notion", "taobao"...
    display_name: str = ""     # 显示名 "Markdown 文件", "Notion 数据库"...
    description: str = ""      # 简短说明
    icon: str = "📄"           # 图标

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def list_items(self) -> list[ContentItem]:
        """列出该来源的所有内容项"""
        ...

    @abstractmethod
    def get_item(self, item_id: str) -> Optional[ContentItem]:
        """获取单个内容项的元数据"""
        ...

    @abstractmethod
    def get_item_content(self, item_id: str) -> str:
        """获取内容项的正文（Markdown 文本）"""
        ...

    def validate_config(self) -> list[str]:
        """验证配置是否完整，返回缺失项列表"""
        return []

    def to_dict(self) -> dict:
        """返回 Provider 信息，供 API/UI 使用"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
        }


# ════════════════════════════════════════════════
# 注册机制（复用 core/publisher.py 相同模式）
# ════════════════════════════════════════════════

_provider_registry: dict[str, type[Provider]] = {}


def register_provider(cls: type[Provider]):
    """装饰器：注册 Provider"""
    _provider_registry[cls.name] = cls
    return cls


def get_provider(name: str, config: Optional[dict] = None) -> Provider:
    """工厂方法：获取 Provider 实例"""
    cls = _provider_registry.get(name)
    if not cls:
        raise KeyError(f"未知 Provider: {name}，可用: {list(_provider_registry.keys())}")
    return cls(config)


def list_providers() -> list[dict]:
    """列出所有已注册的 Provider 信息"""
    return [cls(None).to_dict() for cls in _provider_registry.values()]


def get_provider_names() -> list[str]:
    """返回所有已注册的 Provider 名称列表"""
    return list(_provider_registry.keys())
