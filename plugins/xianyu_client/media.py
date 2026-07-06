"""media upload — 上传图片到闲鱼 CDN（移植自 goofish-cli）"""
from __future__ import annotations

import os
from typing import Any

from .session import USER_AGENT, Session

UPLOAD_URL = "https://stream-upload.goofish.com/api/upload.api"


def upload_image(path: str, session: Session | None = None) -> dict[str, object]:
    """上传单张图片到闲鱼 CDN

    返回: {"url": "...", "width": N, "height": N, "size": N}
    """
    if session is None:
        session = Session.load()

    abs_path = os.path.expanduser(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"图片不存在：{abs_path}")

    headers = {
        "accept": "*/*",
        "origin": "https://www.goofish.com",
        "referer": "https://www.goofish.com/",
        "user-agent": USER_AGENT,
    }
    params = {"floderId": "0", "appkey": "xy_chat", "_input_charset": "utf-8"}

    with open(abs_path, "rb") as f:
        resp = session.http.post(
            UPLOAD_URL,
            headers=headers,
            params=params,
            files={"file": (os.path.basename(abs_path), f, "image/png")},
            timeout=60,
        )
    raw = resp.json()
    obj = raw.get("object") or {}
    pix = str(obj.get("pix", "0x0"))
    try:
        width, height = map(int, pix.split("x"))
    except ValueError:
        width = height = 0
    return {
        "url": obj.get("url", ""),
        "width": width,
        "height": height,
        "size": obj.get("size", 0),
    }


def upload_images(paths: list[str], session: Session | None = None) -> list[dict[str, object]]:
    """批量上传多张图片"""
    results = []
    for p in paths:
        results.append(upload_image(p, session))
    return results
