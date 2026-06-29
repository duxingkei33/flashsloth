"""
AList 网盘存储插件 — 注册到 FS 存储系统
通过 core/storage.py 的注册机制自动接入
"""
# AListStorage 已在 core/storage.py 中用 @register_storage 注册
# 此文件确保插件被导入时触发注册
from flashsloth.core.storage import AlistStorage, LocalStorage, list_storages

__all__ = ["AlistStorage", "LocalStorage", "list_storages"]
