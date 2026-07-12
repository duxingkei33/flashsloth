"""category recommend — AI 识别商品类目（发布前置）

接口：mtop.taobao.idle.kgraph.property.recommend v2.0
"""
from __future__ import annotations

import json
from typing import Any

from .session import Session
from .mtop import call


def recommend(
    title: str,
    images: list[dict[str, Any]] | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    """AI 识别商品类目

    images: [{"url": "...", "width": 1024, "height": 1024}, ...]
    返回: {"cat_id": "...", "cat_name": "...", "channel_cat_id": "...", "tb_cat_id": "...", "confidence": N}
    """
    if session is None:
        session = Session.load()

    if images is None:
        images = []

    image_infos = []
    for img in images:
        image_infos.append({
            "extraInfo": {"isH": "false", "isT": "false", "raw": "false"},
            "isQrCode": False,
            "url": img["url"],
            "heightSize": img["height"],
            "widthSize": img["width"],
            "major": True,
            "type": 0,
            "status": "done",
        })

    raw = call(
        session,
        api="mtop.taobao.idle.kgraph.property.recommend",
        data={
            "title": title,
            "lockCpv": False,
            "multiSKU": False,
            "publishScene": "mainPublish",
            "scene": "newPublishChoice",
            "description": title,
            "imageInfos": image_infos,
            "uniqueCode": "1775905618164677",
        },
        version="2.0",
        spm_cnt="a21ybx.publish.0.0",
    )
    predict = (raw.get("data", {}) or {}).get("categoryPredictResult", {}) or {}
    return {
        "cat_id": str(predict.get("catId", "")),
        "cat_name": predict.get("catName", ""),
        "channel_cat_id": str(predict.get("channelCatId", "")),
        "tb_cat_id": str(predict.get("tbCatId", "")),
        "confidence": predict.get("confidence", 0),
        "raw": raw,
    }
