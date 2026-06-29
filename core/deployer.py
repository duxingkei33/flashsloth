"""
Deployer 基类 + 注册机制
负责将整个静态站点部署到托管平台（GitHub Pages, Netlify, Vercel 等）
设计原则：与 Publisher 平行，职责分离，方便开源扩展
"""
from abc import ABC, abstractmethod
from typing import Optional


_registry: dict[str, type["Deployer"]] = {}


def register(cls):
    """装饰器：注册 Deployer 到全局注册表"""
    _registry[cls.name] = cls
    return cls


def get_deployer(name: str, config: Optional[dict] = None) -> "Deployer":
    """工厂方法：按名称获取 Deployer 实例"""
    if name not in _registry:
        raise KeyError(
            f"未知 Deployer: {name}，可用: {list(_registry.keys())}"
        )
    return _registry[name](config or {})


def list_deployers() -> list[dict]:
    """列出所有已注册的 Deployer 元信息"""
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "description": cls.description,
            "config_fields": cls.config_fields,
        }
        for cls in _registry.values()
    ]


class DeployError(Exception):
    """部署异常"""
    pass


class Deployer(ABC):
    """
    部署器基类。
    所有部署插件必须继承此类并实现 deploy() 方法。

    deploy() 将整个站点源目录部署到托管平台：
    - GitHub Pages: git commit + push
    - Netlify: 触发 webhook 或 CLI
    - Vercel: 触发 webhook 或 CLI
    - 等
    """

    name: str = ""
    display_name: str = ""
    description: str = ""
    config_fields: list[dict] = []

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def deploy(self) -> dict:
        """
        执行完整部署。
        返回: {"success": bool, "url": str, "error": str}
        """
        pass

    def test_connection(self) -> dict:
        """
        测试配置是否有效（可选重写）。
        返回: {"success": bool, "error": str, "status": str}
        """
        return {"success": True, "error": "", "status": "配置有效"}

    def validate_config(self) -> list[str]:
        """验证配置完整性，返回缺失字段列表"""
        missing = []
        for field in self.config_fields:
            if field.get("required", False):
                key = field["key"]
                if not self.config.get(key):
                    missing.append(field.get("label", key))
        return missing

    def get_status_html(self) -> str:
        """返回部署状态摘要 HTML（可选重写）"""
        return f"<span>{self.display_name}</span>"
