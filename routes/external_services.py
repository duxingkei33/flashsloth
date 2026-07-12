"""
FlashSloth — 外部服务集成路由

管理外部服务（如 xianyu-auto-reply）的管理入口链接和状态监控。
"""
import os
import json
import requests
from datetime import datetime

from flask import render_template, jsonify
from flask_login import login_required

from flashsloth.routes._app import app

# 已安装的外部服务注册表
EXTERNAL_SERVICES = []


def register_service(name: str, display_name: str, icon: str,
                     frontend_url: str, backend_url: str,
                     description: str = "",
                     health_endpoint: str = "/health"):
    """
    注册外部服务到 FlashSloth 管理面板。

    参数:
        name:            服务唯一标识
        display_name:    显示名称
        icon:            图标 emoji
        frontend_url:    前端页面地址
        backend_url:    后端 API 地址
        description:     描述文字
        health_endpoint: 健康检查端点
    """
    EXTERNAL_SERVICES.append({
        "name": name,
        "display_name": display_name,
        "icon": icon,
        "frontend_url": frontend_url,
        "backend_url": backend_url,
        "description": description,
        "health_endpoint": health_endpoint,
        "registered_at": datetime.now().isoformat(),
    })


# ─── 注册 xianyu-auto-reply ──────────────────────
XY_BACKEND = os.environ.get("XY_AUTO_REPLY_URL", "http://localhost:8089")
XY_FRONTEND = os.environ.get("XY_AUTO_REPLY_FRONTEND", "http://localhost:9000")

register_service(
    name="xianyu_auto_reply",
    display_name="闲鱼自动回复",
    icon="🐟",
    frontend_url=XY_FRONTEND,
    backend_url=XY_BACKEND,
    description="zhinianboke/xianyu-auto-reply — 多账号闲鱼自动回复/商品发布/订单管理",
    health_endpoint="/health",
)


# ─── API 路由 ─────────────────────────────────

@app.route("/api/external-services")
@login_required
def api_external_services():
    """获取所有已注册的外部服务及其状态"""
    result = []
    for svc in EXTERNAL_SERVICES:
        status = _check_service_health(svc["backend_url"], svc.get("health_endpoint", "/health"))
        result.append({
            **svc,
            "status": status,
        })
    return jsonify({"success": True, "services": result})


def _check_service_health(base_url: str, endpoint: str) -> dict:
    """检查外部服务健康状态"""
    try:
        resp = requests.get(f"{base_url}{endpoint}", timeout=5)
        if resp.status_code == 200:
            return {"online": True, "code": resp.status_code, "error": ""}
        return {"online": False, "code": resp.status_code, "error": f"HTTP {resp.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"online": False, "code": 0, "error": "无法连接"}
    except Exception as e:
        return {"online": False, "code": 0, "error": str(e)}
