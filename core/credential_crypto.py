"""
FlashSloth — 凭证加密存储模块

使用 Fernet (AES-128-CBC + HMAC-SHA256) 对称加密：
- 密钥 => ~/.hermes/flashsloth/.fs_key（不存在则自动生成）
- 环境变量 FS_ENCRYPTION_KEY 可覆盖
- 加密字段：password, cookie, token, app_secret, api_key, access_token, refresh_token

用法：
    from core.credential_crypto import encrypt_config, decrypt_config
    encrypted = encrypt_config(raw_cfg)
    decrypted = decrypt_config(encrypted_cfg)
"""

import os
import json
import base64
from pathlib import Path

# 需要加密的敏感字段
SENSITIVE_FIELDS = {
    "password", "cookie", "token", "app_secret",
    "api_key", "access_token", "refresh_token",
}

# 加密后字段的前缀标记
ENCRYPTED_PREFIX = "enc:"


def _get_or_create_key() -> bytes:
    """获取或生成加密密钥"""
    # 1. 环境变量优先
    env_key = os.environ.get("FS_ENCRYPTION_KEY")
    if env_key:
        try:
            return base64.urlsafe_b64decode(env_key.encode())
        except Exception:
            pass

    # 2. 密钥文件
    key_path = Path(__file__).resolve().parent.parent / ".fs_key"
    if key_path.exists():
        raw = key_path.read_text().strip()
        try:
            return base64.urlsafe_b64decode(raw.encode())
        except Exception:
            pass

    # 3. 生成新密钥
    from cryptography.fernet import Fernet
    key = Fernet.generate_key()
    key_path.write_text(key.decode())
    key_path.chmod(0o600)  # 只有owner可读
    print(f"[credential_crypto] 🔑 新加密密钥已生成: {key_path}")
    return base64.urlsafe_b64decode(key.decode())


def _get_fernet():
    """获取 Fernet 实例"""
    from cryptography.fernet import Fernet
    key = _get_or_create_key()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_value(plaintext: str) -> str:
    """加密单个敏感值，返回 enc:base64密文"""
    if not plaintext:
        return ""
    f = _get_fernet()
    encrypted = f.encrypt(plaintext.encode("utf-8"))
    return ENCRYPTED_PREFIX + base64.urlsafe_b64encode(encrypted).decode()


def decrypt_value(encrypted: str) -> str:
    """解密单个 enc: 前缀的密文"""
    if not encrypted or not encrypted.startswith(ENCRYPTED_PREFIX):
        return encrypted  # 非加密格式，原样返回（兼容旧数据）
    try:
        f = _get_fernet()
        raw = base64.urlsafe_b64decode(encrypted[len(ENCRYPTED_PREFIX):])
        return f.decrypt(raw).decode("utf-8")
    except Exception:
        return encrypted  # 解密失败时原样返回


def encrypt_config(cfg: dict) -> dict:
    """加密配置中所有敏感字段（就地修改）"""
    for k in list(cfg.keys()):
        kl = k.lower()
        if kl in SENSITIVE_FIELDS and isinstance(cfg[k], str) and cfg[k]:
            # 避免重复加密
            if not cfg[k].startswith(ENCRYPTED_PREFIX):
                cfg[k] = encrypt_value(cfg[k])
    return cfg


def decrypt_config(cfg: dict) -> dict:
    """解密配置中所有敏感字段（就地修改）"""
    for k in list(cfg.keys()):
        kl = k.lower()
        if kl in SENSITIVE_FIELDS and isinstance(cfg[k], str) and cfg[k]:
            cfg[k] = decrypt_value(cfg[k])
    return cfg
