"""Cookie 加密存储 + Session 管理 — 移植自 goofish-cli

登录态解析顺序：
1. cookies.json 存在且有效 → 直接用
2. cookies.json 不存在 → 从本机浏览器自动导入
3. 浏览器也抓不到 → 抛 AuthRequiredError
"""
from __future__ import annotations

import hashlib
import json
import getpass
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from .errors import AuthRequiredError
from .sign import generate_device_id

try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

FLASHSLOTH_HOME = Path(os.environ.get("FLASHSLOTH_HOME", Path.home() / ".hermes" / "flashsloth"))
DEFAULT_COOKIE_PATH = FLASHSLOTH_HOME / "xianyu_cookies.json"
DEVICE_CACHE_PATH = FLASHSLOTH_HOME / "xianyu_device.json"
ENCRYPT_SALT = b"flashsloth-xianyu-cookie-enc-v1"
ENCRYPT_ITERATIONS = 480_000

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)

# 闲鱼 / 淘系登录态必要字段
REQUIRED_KEYS = ("_m_h5_tk", "unb", "cookie2")
GOOFISH_DOMAINS = ("goofish.com", "taobao.com")


def _machine_key() -> bytes:
    """从 hostname + username 派生机器密钥"""
    raw = f"{platform.node()}:{getpass.getuser()}:flashsloth-xianyu".encode()
    dk = hashlib.pbkdf2_hmac("sha256", raw, ENCRYPT_SALT, ENCRYPT_ITERATIONS)
    import base64
    return base64.urlsafe_b64encode(dk)


def encrypt_cookies(cookies: dict[str, str]) -> bytes:
    """加密 cookies（Fernet AES-128-CBC + HMAC-SHA256）"""
    if not HAS_CRYPTO:
        return json.dumps(cookies, ensure_ascii=False).encode()
    payload = json.dumps(cookies, ensure_ascii=False).encode()
    return Fernet(_machine_key()).encrypt(payload)


def decrypt_cookies(data: bytes) -> dict[str, str]:
    """解密 cookies"""
    if not HAS_CRYPTO:
        try:
            return json.loads(data.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        return {}
    try:
        plain = Fernet(_machine_key()).decrypt(data)
        return json.loads(plain)
    except InvalidToken:
        # 尝试明文（兼容旧格式）
        try:
            return json.loads(data.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("cookie 解密失败（可能在其他机器上加密的）")


def resolve_cookie_path(cookie_path: Path | str | None = None) -> Path:
    """解析实际 cookie 文件路径"""
    return Path(
        os.path.expanduser(str(cookie_path)) if cookie_path
        else os.environ.get("XIANYU_COOKIES_PATH") or str(DEFAULT_COOKIE_PATH)
    )


def write_cookies_json(path: Path, cookies: dict[str, str]) -> None:
    """加密写盘 cookies"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypt_cookies(cookies))
    path.chmod(0o600)


def _load_or_mint_device_id(unb: str) -> str:
    """device_id 必须在 unb 维度稳定（IM WebSocket token 绑定）"""
    if DEVICE_CACHE_PATH.exists():
        try:
            raw = json.loads(DEVICE_CACHE_PATH.read_text())
            if raw.get("unb") == unb and raw.get("device_id"):
                return raw["device_id"]
        except (json.JSONDecodeError, OSError):
            pass
    device_id = generate_device_id(unb)
    DEVICE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEVICE_CACHE_PATH.write_text(json.dumps({"unb": unb, "device_id": device_id}))
    DEVICE_CACHE_PATH.chmod(0o600)
    return device_id


def _load_cookies(path: Path) -> dict[str, str]:
    """从文件加载 cookies（自动识别加密 / 明文）"""
    if not path.exists():
        return {}
    raw_bytes = path.read_bytes()
    try:
        return decrypt_cookies(raw_bytes)
    except (ValueError, Exception):
        pass
    try:
        raw = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise AuthRequiredError(f"cookie 文件格式不识别：{path}") from e
    if isinstance(raw, list):
        return {c["name"]: c["value"] for c in raw if "name" in c and "value" in c}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    raise AuthRequiredError(f"cookies.json 格式不识别：{path}")


@dataclass
class Session:
    """闲鱼 API Session"""
    http: requests.Session
    unb: str
    tracknick: str = ""
    device_id: str = ""

    @classmethod
    def load(cls, cookie_path: Path | str | None = None) -> Session:
        path = resolve_cookie_path(cookie_path)
        cookies = _load_cookies(path)

        if "unb" not in cookies or "_m_h5_tk" not in cookies:
            raise AuthRequiredError(
                f"cookie 缺失 unb / _m_h5_tk，请先在浏览器登录 https://www.goofish.com "
                f"后导出 cookie 到 {path}"
            )

        http = requests.Session()
        http.cookies.update(cookies)
        return cls(
            http=http,
            unb=cookies["unb"],
            tracknick=cookies.get("tracknick", ""),
            device_id=_load_or_mint_device_id(cookies["unb"]),
        )

    @property
    def h5_token(self) -> str:
        raw = self.http.cookies.get("_m_h5_tk", "")
        return raw.split("_")[0] if raw else ""

    def get_cookie(self, name: str) -> str:
        return self.http.cookies.get(name, "")

    def to_dict(self) -> dict[str, str]:
        """展平所有 cookie 为 dict"""
        return {name: value for name, value in self.http.cookies.items() if value}

    def save(self, path: Path | None = None) -> None:
        """保存当前 session cookies 到文件"""
        p = resolve_cookie_path(path)
        write_cookies_json(p, self.to_dict())
