"""Signin 基类 + 注册机制

可扩展的签到系统：每个论坛平台实现自己的签到插件，
继承 SigninBase 并用 @register 装饰器注册。
"""
from abc import ABC, abstractmethod
from typing import Optional


class SigninError(Exception):
    """签到异常"""
    pass


class SigninBase(ABC):
    """所有签到插件必须继承此类"""

    name: str = ""                     # 唯一标识，如 "discuz_k_misign"
    display_name: str = ""             # 显示名，如 "Discuz! 签到 (k_misign)"
    platform: str = ""                 # 对应平台，如 "discuz"
    config_fields: list[dict] = []     # 额外配置字段

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def signin(self) -> dict:
        """
        执行签到
        返回: {
            "success": bool,
            "already_signed": bool,  # 今天是否已签到
            "error": str,
            "message": str,
        }
        """
        pass

    def can_handle(self, account: dict) -> bool:
        """判断此插件是否能处理该账号"""
        return account.get("platform", "") == self.platform

    def validate(self) -> list[str]:
        """返回缺失的配置项"""
        missing = []
        for field in self.config_fields:
            key = field.get("key")
            required = field.get("required", False)
            if required and not self.config.get(key):
                missing.append(key)
        return missing


# === 注册中心 ===
_registry: dict[str, type[SigninBase]] = {}


def register(cls: type[SigninBase]):
    """装饰器：注册 Signin 插件"""
    _registry[cls.name] = cls
    return cls


def get_signin(name: str, config: Optional[dict] = None) -> SigninBase:
    """工厂方法：获取 Signin 实例"""
    cls = _registry.get(name)
    if not cls:
        raise KeyError(f"未知 Signin: {name}，可用: {list(_registry.keys())}")
    return cls(config)


def get_signin_for_account(account: dict) -> Optional[SigninBase]:
    """根据账号自动匹配合适的签到插件"""
    for name, cls in _registry.items():
        instance = cls(account.get("config", {}))
        if instance.can_handle(account):
            return instance
    return None


def list_signins() -> list[dict]:
    """列出所有已注册的 Signin 信息"""
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "platform": cls.platform,
            "config_fields": cls.config_fields,
        }
        for cls in _registry.values()
    ]
