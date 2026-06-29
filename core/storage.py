"""
统一存储抽象层 — 支持本地存储和 AList 远程存储
设计：所有文件操作统一接口，文章资源自动按类型归档
"""
from __future__ import annotations
import os, json, time, hashlib, uuid
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import quote
from typing import List


# ─── 文件分类 ────────────────────────────────────
FILE_CATEGORIES = {
    "image": ["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico"],
    "video": ["mp4", "avi", "mkv", "mov", "wmv", "flv", "webm"],
    "audio": ["mp3", "wav", "ogg", "aac", "flac", "m4a"],
    "document": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "md", "txt"],
    "resource": ["zip", "rar", "7z", "tar", "gz", "iso"],
    "other": [],
}


def get_category(filename: str) -> str:
    """根据文件名判断分类"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for cat, exts in FILE_CATEGORIES.items():
        if ext in exts:
            return cat
    return "other"


def make_path(category: str, article_id: int | None = None, filename: str = "") -> str:
    """生成统一路径：/类型/文章ID/文件名"""
    parts = [f"/{category}"]
    if article_id:
        parts.append(str(article_id))
    if filename:
        parts.append(filename)
    return "/".join(parts)


# ─── 存储后端注册 ────────────────────────────────
_storage_backends: dict[str, type["StorageBackend"]] = {}


def register_storage(cls):
    """装饰器：注册存储后端"""
    _storage_backends[cls.name] = cls
    return cls


def get_storage(name: str, config: dict) -> "StorageBackend":
    """获取存储后端实例"""
    cls = _storage_backends.get(name)
    if not cls:
        raise ValueError(f"未知存储后端: {name}，可用: {list(_storage_backends.keys())}")
    return cls(config)


def list_storages() -> list[dict]:
    """列出所有可用存储后端"""
    return [
        {"name": name, "display_name": cls.display_name, "config_fields": cls.config_fields}
        for name, cls in _storage_backends.items()
    ]


# ─── 抽象基类 ────────────────────────────────────
class StorageBackend(ABC):
    """存储后端抽象基类"""

    name: str = ""
    display_name: str = ""
    config_fields: list[dict] = []

    def __init__(self, config: dict):
        self.config = config
        self.base_path = config.get("base_path", "/flashsloth").rstrip("/")

    @abstractmethod
    def test_connection(self) -> dict:
        """测试连接是否可用"""
        ...

    @abstractmethod
    def upload(self, local_path: str, remote_path: str) -> dict:
        """上传文件到远程路径"""
        ...

    @abstractmethod
    def upload_bytes(self, data: bytes, remote_path: str) -> dict:
        """直接上传字节数据"""
        ...

    @abstractmethod
    def list(self, path: str = "/") -> list[dict]:
        """列出目录内容"""
        ...

    @abstractmethod
    def mkdir(self, path: str) -> bool:
        """创建目录"""
        ...

    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件或空目录"""
        ...

    @abstractmethod
    def get_url(self, path: str) -> str:
        """获取文件下载/访问 URL"""
        ...

    def full_path(self, path: str) -> str:
        """拼接 base_path"""
        p = f"{self.base_path}{path}" if not path.startswith(self.base_path) else path
        return p.replace("//", "/")

    def ensure_category_dir(self, category: str) -> str:
        """确保分类目录存在，返回路径"""
        path = f"/{category}"
        self.mkdir(self.full_path(path))
        return path

    def upload_article_attachment(self, local_path: str, article_id: int, filename: str = "") -> dict:
        """上传文章附件，自动归类"""
        if not filename:
            filename = os.path.basename(local_path)
        cat = get_category(filename)
        self.ensure_category_dir(cat)
        remote = make_path(cat, article_id, filename)
        return self.upload(local_path, self.full_path(remote))

    def upload_image_data(self, data: bytes, article_id: int, ext: str = "png") -> dict:
        """上传图片字节数据（用于编辑器粘贴上传）"""
        filename = f"{uuid.uuid4().hex[:12]}.{ext}"
        return self.upload_article_attachment_bytes(data, article_id, filename)

    def upload_article_attachment_bytes(self, data: bytes, article_id: int, filename: str) -> dict:
        """上传文章附件（字节流），自动归类"""
        cat = get_category(filename)
        self.ensure_category_dir(cat)
        remote = make_path(cat, article_id, filename)
        return self.upload_bytes(data, self.full_path(remote))

    def list_article_attachments(self, article_id: int) -> list[dict]:
        """列出文章的所有附件"""
        results = []
        for cat in FILE_CATEGORIES:
            if cat == "other":
                continue
            path = make_path(cat, article_id)
            try:
                items = self.list(self.full_path(path))
                for item in items:
                    item["category"] = cat
                results.extend(items)
            except Exception:
                pass
        return results


# ─── 本地存储 ────────────────────────────────────
@register_storage
class LocalStorage(StorageBackend):
    """本地文件系统存储（开发/测试用）"""

    name = "local"
    display_name = "本地存储"
    config_fields = [
        {"key": "root_path", "label": "本地根目录", "type": "text", "required": True,
         "placeholder": "/opt/data/flashsloth/storage"},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.root = config.get("root_path", "/opt/data/flashsloth/storage")
        os.makedirs(self.root, exist_ok=True)

    def _resolve(self, path: str) -> str:
        p = self.full_path(path).lstrip("/")
        full = os.path.join(self.root, p)
        # 安全检查：不允许跳出 root
        real = os.path.realpath(full)
        if not real.startswith(os.path.realpath(self.root)):
            raise PermissionError(f"路径越权: {path}")
        return full

    def test_connection(self) -> dict:
        try:
            os.makedirs(self.root, exist_ok=True)
            test_file = os.path.join(self.root, ".fs_test")
            open(test_file, "w").close()
            os.remove(test_file)
            return {"success": True, "status": "本地存储正常"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def upload(self, local_path: str, remote_path: str) -> dict:
        dest = self._resolve(remote_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(local_path, "rb") as src:
            data = src.read()
        with open(dest, "wb") as dst:
            dst.write(data)
        return {"success": True, "path": remote_path, "size": len(data)}

    def upload_bytes(self, data: bytes, remote_path: str) -> dict:
        dest = self._resolve(remote_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        return {"success": True, "path": remote_path, "size": len(data)}

    def list(self, path: str = "/") -> list[dict]:
        dir_path = self._resolve(path)
        if not os.path.isdir(dir_path):
            return []
        items = []
        for name in sorted(os.listdir(dir_path)):
            full = os.path.join(dir_path, name)
            is_dir = os.path.isdir(full)
            items.append({
                "name": name,
                "is_dir": is_dir,
                "size": 0 if is_dir else os.path.getsize(full),
                "modified": os.path.getmtime(full) if not is_dir else 0,
            })
        return items

    def mkdir(self, path: str) -> bool:
        os.makedirs(self._resolve(path), exist_ok=True)
        return True

    def delete(self, path: str) -> bool:
        full = self._resolve(path)
        if os.path.isfile(full):
            os.remove(full)
            return True
        if os.path.isdir(full):
            os.rmdir(full) if not os.listdir(full) else None
            return True
        return False

    def get_url(self, path: str) -> str:
        # 本地模式返回文件路径
        return self._resolve(path)


# ─── AList 远程存储 ──────────────────────────────
@register_storage
class AlistStorage(StorageBackend):
    """AList API 远程存储"""

    name = "alist"
    display_name = "AList 网盘"
    config_fields = [
        {"key": "server_url", "label": "AList 服务器地址", "type": "text", "required": True,
         "placeholder": "https://alist.example.com"},
        {"key": "token", "label": "API Token", "type": "password", "required": True,
         "placeholder": "从 AList 后台获取或登录获取"},
        {"key": "base_path", "label": "存储根路径", "type": "text", "required": False,
         "placeholder": "/flashsloth（默认为 /flashsloth）"},
        {"key": "username", "label": "用户名（自动获取Token用）", "type": "text", "required": False},
        {"key": "password", "label": "密码（自动获取Token用）", "type": "password", "required": False},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.server = config.get("server_url", "").rstrip("/")
        self._token = config.get("token", "")
        self.username = config.get("username", "")
        self.password = config.get("password", "")

    def _headers(self) -> dict:
        return {
            "Authorization": self._token,
            "User-Agent": "FlashSloth/1.0",
            "Content-Type": "application/json",
        }

    def _api_post(self, endpoint: str, data: dict = None) -> dict:
        """调用 AList API"""
        import requests
        url = f"{self.server}/api{endpoint}"
        resp = requests.post(url, json=data or {}, headers=self._headers(), timeout=30)
        result = resp.json()
        if result.get("code") != 200:
            raise Exception(f"AList API 错误: {result.get('message', '未知错误')}")
        return result.get("data", {})

    def _api_get(self, endpoint: str, params: dict = None) -> dict:
        """GET 请求 AList API"""
        import requests
        url = f"{self.server}/api{endpoint}"
        resp = requests.get(url, params=params or {}, headers=self._headers(), timeout=30)
        result = resp.json()
        if result.get("code") != 200:
            raise Exception(f"AList API 错误: {result.get('message', '未知错误')}")
        return result.get("data", {})

    def _refresh_token(self) -> bool:
        """用用户名密码刷新 token"""
        if not self.username or not self.password:
            return False
        import requests
        try:
            resp = requests.post(
                f"{self.server}/api/auth/login",
                json={"username": self.username, "password": self.password},
                timeout=15,
            )
            result = resp.json()
            if result.get("code") == 200:
                self._token = result["data"]["token"]
                return True
        except Exception:
            pass
        return False

    def test_connection(self) -> dict:
        try:
            # 尝试获取用户信息验证 token
            data = self._api_get("/me")
            return {"success": True, "status": f"已连接 - {data.get('username', '未知用户')}"}
        except Exception as e:
            # 尝试刷新 token
            if self._refresh_token():
                try:
                    data = self._api_get("/me")
                    return {"success": True, "status": f"已连接（Token已刷新） - {data.get('username', '未知用户')}"}
                except Exception as e2:
                    return {"success": False, "error": f"连接失败: {e2}"}
            return {"success": False, "error": f"连接失败: {e}"}

    def upload(self, local_path: str, remote_path: str) -> dict:
        """通过表单上传文件"""
        import requests
        path = self.full_path(remote_path)
        encoded_path = quote(path, safe="")

        with open(local_path, "rb") as f:
            file_data = f.read()

        url = f"{self.server}/api/fs/form"
        headers = {
            "Authorization": self._token,
            "File-Path": encoded_path,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(file_data)),
            "As-Task": "false",
        }
        resp = requests.put(url, data=file_data, headers=headers, timeout=120)
        result = resp.json()
        if result.get("code") != 200:
            raise Exception(f"上传失败: {result.get('message', '未知错误')}")
        return {"success": True, "path": remote_path, "size": len(file_data)}

    def upload_bytes(self, data: bytes, remote_path: str) -> dict:
        """直接上传字节数据"""
        import requests
        path = self.full_path(remote_path)
        encoded_path = quote(path, safe="")

        url = f"{self.server}/api/fs/form"
        headers = {
            "Authorization": self._token,
            "File-Path": encoded_path,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
            "As-Task": "false",
        }
        resp = requests.put(url, data=data, headers=headers, timeout=120)
        result = resp.json()
        if result.get("code") != 200:
            raise Exception(f"上传失败: {result.get('message', '未知错误')}")
        return {"success": True, "path": remote_path, "size": len(data)}

    def list(self, path: str = "/") -> list[dict]:
        data = self._api_post("/fs/list", {
            "path": self.full_path(path),
            "page": 1,
            "per_page": 200,
            "refresh": False,
        })
        items = []
        for item in data.get("content", []):
            items.append({
                "name": item["name"],
                "is_dir": item.get("is_dir", False),
                "size": item.get("size", 0),
                "modified": item.get("modified", ""),
                "thumb": item.get("thumb", ""),
            })
        return items

    def mkdir(self, path: str) -> bool:
        try:
            self._api_post("/fs/mkdir", {"path": self.full_path(path)})
            return True
        except Exception:
            return False

    def delete(self, path: str) -> bool:
        full = self.full_path(path)
        dir_path = "/".join(full.split("/")[:-1])
        name = full.split("/")[-1]
        try:
            self._api_post("/fs/remove", {"names": [name], "dir": dir_path})
            return True
        except Exception:
            return False

    def get_url(self, path: str) -> str:
        """获取 AList 上文件的直接下载链接"""
        full = self.full_path(path)
        try:
            data = self._api_post("/fs/link", {"path": full})
            return data.get("url", "")
        except Exception:
            return f"{self.server}{full}"
