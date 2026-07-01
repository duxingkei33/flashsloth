"""
FlashSloth SDK — 统一平台适配器基类

每个平台实现一个 Adapter，继承 PlatformAdapter，定义该平台支持的所有能力。
不支持的接口返回 {"supported": False} 即可，无需实现。

第三方开发者适配新平台只需写一个文件：
```python
from flashsloth.sdk import PlatformAdapter

class MyForumAdapter(PlatformAdapter):
    name = "my_forum"
    display_name = "我的论坛"
    ...
```
"""
from abc import ABC, abstractmethod
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json


# ═══════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════

@dataclass
class Article:
    """统一文章模型 — 所有平台输入输出都转成此格式"""
    title: str = ""
    body: str = ""                    # Markdown 正文
    summary: str = ""                 # 摘要
    tags: list = field(default_factory=list)
    source: str = ""                  # 来源平台名 (如 "mydigit", "notion")
    source_url: str = ""              # 原文链接
    source_id: str = ""               # 原文 ID
    author: str = ""                  # 原作者
    created_at: Optional[str] = None
    images: list = field(default_factory=list)   # 图片 URL 列表
    attachments: list = field(default_factory=list)  # 附件列表
    raw: dict = field(default_factory=dict)       # 原始数据（调试用）

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


@dataclass
class Comment:
    """回复/评论模型"""
    id: str = ""
    author: str = ""
    content: str = ""
    created_at: Optional[str] = None
    parent_id: str = ""               # 回复的评论 ID（空=直接回复主题）
    thread_id: str = ""               # 所属主题 ID


@dataclass
class PlatformInfo:
    """平台信息"""
    name: str
    display_name: str
    site_url: str = ""
    version: str = "1.0.0"
    description: str = ""


# ═══════════════════════════════════════════════
# 平台适配器基类
# ═══════════════════════════════════════════════

class PlatformAdapter(ABC):
    """
    统一平台适配器基类。

    一个平台 = 一个文件 = 一个 Adapter 类。
    不支持的接口返回 {"supported": False}，不强制实现。
    """

    name: str = ""                     # 唯一标识，如 "mydigit"
    display_name: str = ""             # 显示名，如 "数码之家"
    site_url: str = ""                 # 网站地址
    version: str = "1.0.0"
    description: str = ""
    config_fields: list[dict] = []     # 后台配置字段
    author: str = ""
    icon: str = "🌐"                   # 默认图标

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    # ─── 必选：平台信息 ────────────────────────
    def get_info(self) -> PlatformInfo:
        return PlatformInfo(
            name=self.name,
            display_name=self.display_name,
            site_url=self.site_url,
            version=self.version,
            description=self.description,
        )

    # ─── 能力声明 ────────────────────────────
    def capabilities(self) -> list[str]:
        """
        返回此适配器支持的所有能力列表。
        自动检测：遍历 self 的方法，检查是否返回 {"supported": False}
        """
        caps = []
        # 默认所有 adapter 都支持这些能力检测
        checks = [
            ("sign_in", "签到"),
            ("publish", "发布"),
            ("retract", "撤回"),
            ("fetch_posts", "采集帖子"),
            ("fetch_replies", "采集回复"),
            ("fetch_thread_detail", "读帖详情"),
            ("reply_comment", "回复评论"),
            ("browse_forum", "逛论坛"),
            ("deploy", "部署"),
        ]
        for method_name, cap_name in checks:
            method = getattr(self, method_name, None)
            if method:
                try:
                    result = method(check_only=True)
                    if result.get("supported", True):
                        caps.append(cap_name)
                except Exception:
                    caps.append(cap_name)
        return caps

    # ─── 签到 ─────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """
        每日签到。
        check_only=True 时只检查是否支持，不执行。
        返回: {"supported": bool, "success": bool, "already_signed": bool, "error": str, "message": str}
        """
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────
    def publish(self, article: Article, **kwargs) -> dict:
        """
        发布文章到本平台。
        返回: {"supported": bool, "success": bool, "url": str, "id": str, "error": str, "message": str}
        """
        return {"supported": False}

    # ─── 撤回 ─────────────────────────────────
    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """
        撤回已发布的文章。
        返回: {"supported": bool, "success": bool, "error": str, "message": str}
        """
        return {"supported": False}

    # ─── 采集 ─────────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """
        从本平台采集新帖/新内容。
        返回文章列表，空列表 = 无新内容。
        """
        return []

    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """
        采集回复/评论。
        """
        return []

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """
        获取单篇帖子的详细内容。
        """
        return None

    # ─── 互动 ─────────────────────────────────
    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """
        回复评论/帖子。
        返回: {"supported": bool, "success": bool, "error": str, "message": str}
        """
        return {"supported": False}

    # ─── 逛论坛 ───────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """
        浏览论坛，推荐感兴趣的内容。
        返回: {"supported": bool, "total": int, "filtered": int, "new_saved": int, "forums": list}
        """
        return {"supported": False}

    # ─── 部署 ─────────────────────────────────
    def deploy(self, **kwargs) -> dict:
        """
        部署站点（如 GitHub Pages）。
        返回: {"supported": bool, "success": bool, "url": str, "error": str, "message": str}
        """
        return {"supported": False}

    # ─── 工具方法 ─────────────────────────────
    def validate_config(self) -> list[str]:
        """返回缺失的配置项"""
        missing = []
        for field in self.config_fields:
            key = field.get("key")
            required = field.get("required", False)
            if required and not self.config.get(key):
                missing.append(field.get("label", key))
        return missing

    def test_connection(self) -> dict:
        """
        测试账号配置是否可用。
        返回: {"supported": bool, "success": bool, "error": str, "status": str}
        """
        return {"supported": True, "success": True, "error": "", "status": "未实现"}


# ═══════════════════════════════════════════════
# 注册中心
# ═══════════════════════════════════════════════

_registry: dict[str, type[PlatformAdapter]] = {}
# 别名映射：旧平台名 → 新 adapter name（兼容旧数据）
_aliases: dict[str, str] = {}


def register(cls: type[PlatformAdapter]):
    """装饰器：注册 PlatformAdapter"""
    _registry[cls.name] = cls
    return cls


def alias(old_name: str):
    """装饰器：为 adapter 注册别名（兼容旧配置中的平台名）"""
    def wrapper(cls: type[PlatformAdapter]):
        _aliases[old_name] = cls.name
        return cls
    return wrapper


def get_adapter(name: str, config: Optional[dict] = None) -> Optional[PlatformAdapter]:
    """工厂方法：获取 Adapter 实例"""
    real_name = _aliases.get(name, name)
    cls = _registry.get(real_name)
    if not cls:
        return None
    return cls(config)


def get_adapter_for_account(account: dict) -> Optional[PlatformAdapter]:
    """
    根据 platform_accounts 中的记录自动匹配 Adapter。
    先查 name 精确匹配，再查别名。
    """
    name = account.get("platform", "")
    cfg = account.get("config", {})
    return get_adapter(name, cfg)


def list_adapters() -> list[PlatformInfo]:
    """列出所有已注册的 Adapter"""
    result = []
    for cls in _registry.values():
        inst = cls()
        info = inst.get_info()
        info_dict = {
            "name": info.name,
            "display_name": info.display_name,
            "site_url": info.site_url,
            "version": info.version,
            "description": info.description,
            "capabilities": inst.capabilities(),
            "config_fields": cls.config_fields,
            "icon": getattr(cls, "icon", "🌐"),
        }
        result.append(info_dict)
    return result


def get_db():
    """获取 FlashSloth DB 连接（供 adapter 内部使用）"""
    import sqlite3, os
    db_path = os.environ.get("FLASHSLOTH_DB_PATH") or \
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
