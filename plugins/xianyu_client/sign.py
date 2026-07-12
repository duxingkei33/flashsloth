"""MTOP 签名生成 — 纯 Python 移植自 goofish-cli JS 引擎"""
import hashlib
import random
import time
import uuid as uuid_mod

_APP_KEY = "34839810"
_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def generate_sign(t: str, token: str, data: str) -> str:
    """生成 MTOP 请求签名

    算法：MD5(token + "&" + t + "&" + appKey + "&" + data)
    """
    msg = f"{token}&{t}&{_APP_KEY}&{data}"
    return hashlib.md5(msg.encode()).hexdigest()


def generate_device_id(user_id: str) -> str:
    """生成设备 ID（绑定 user_id 以保持稳定）"""
    parts = []
    for i in range(36):
        if i in (8, 13, 18, 23):
            parts.append("-")
        elif i == 14:
            parts.append("4")
        else:
            r = int(16 * random.random())
            c = _CHARS[19 if i == 19 else (3 & r | 8) if i == 19 else r]
            parts.append(c)
    return "".join(parts) + "-" + user_id


def generate_mid() -> str:
    """生成消息 ID"""
    return f"{int(1e3 * random.random())}{int(time.time() * 1000)} 0"


def generate_uuid() -> str:
    """生成 UUID"""
    return f"-{int(time.time() * 1000)}1"


def generate_utdid() -> str:
    """生成本机 UTDID（设备指纹）"""
    mac_parts = ["%02x" % random.randint(0, 255) for _ in range(6)]
    return mac_parts[0] + ":" + mac_parts[1] + ":" + mac_parts[2] + ":" + \
           mac_parts[3] + ":" + mac_parts[4] + ":" + mac_parts[5]
