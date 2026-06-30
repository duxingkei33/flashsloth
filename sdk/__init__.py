"""
FlashSloth SDK — 统一平台适配器

```python
from flashsloth.sdk import PlatformAdapter, Article, register, get_adapter, list_adapters

class MyAdapter(PlatformAdapter):
    name = "my_platform"
    ...
```
"""
import os, sys

# 确保 flashsloth 包可导入（兼容 admin.py 和独立脚本两种运行方式）
_sdk_root = os.path.dirname(os.path.abspath(__file__))   # sdk/
_fs_root = os.path.dirname(_sdk_root)                     # flashsloth/
_fs_parent = os.path.dirname(_fs_root)                    # flashsloth 的父目录
if _fs_parent not in sys.path:
    sys.path.insert(0, _fs_parent)

from .adapter import (
    PlatformAdapter, Article, Comment, PlatformInfo,
    register, alias, get_adapter, get_adapter_for_account, list_adapters, get_db,
)
from .router import Router, RouteRule

__all__ = [
    "PlatformAdapter", "Article", "Comment", "PlatformInfo",
    "register", "alias", "get_adapter", "get_adapter_for_account",
    "list_adapters", "get_db",
    "Router", "RouteRule",
]
