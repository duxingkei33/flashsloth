"""FlashSloth Playwright 浏览器引擎 — API 路由

提供浏览器引擎的启停控制、状态查询、配置管理和心跳保活。

端点一览：
  POST /api/browser/start     → 启动浏览器
  POST /api/browser/stop      → 停止浏览器
  POST /api/browser/restart   → 重启浏览器
  GET  /api/browser/status    → 获取状态（状态文本+详细数据）
  POST /api/browser/keepalive → 标记活动
  GET  /api/browser/config    → 获取配置
  POST /api/browser/config    → 更新配置
"""

from __future__ import annotations

import json
import logging
import time

from flask import jsonify, render_template, request
from flask_login import login_required, current_user

from flashsloth.routes._app import app
from flashsloth.core.browser_engine import BrowserEngine, get_engine

logger = logging.getLogger(__name__)


# ─── 全局上下文注入 ───────────────────────────

@app.context_processor
def inject_browser_engine_status():
    """注入浏览器引擎状态到所有模板（直接读取状态字段，避免锁争用）"""
    try:
        from flask_login import current_user
        if not current_user.is_authenticated:
            return {
                "pw_status": "stopped",
                "pw_badge_class": "badge-secondary",
                "pw_badge_text": "🖥️ 已停止",
                "pw_tabs_count": 0,
            }
        engine = get_engine()
        # 超时锁读取状态，避免引擎启动卡死时阻塞所有页面
        locked = engine._lock.acquire(timeout=3.0)
        if locked:
            try:
                st = engine._status
                tabs = len(engine._context.pages) if engine._context else 0
            finally:
                engine._lock.release()
        else:
            st = "stopped"
            tabs = 0
        badge_cls, badge_text = {
            "starting": ("badge-warning", "🖥️ 启动中"),
            "ready": ("badge-success", "🖥️ 已就绪"),
            "restarting": ("badge-warning", "🖥️ 重启中"),
            "error": ("badge-danger", "🖥️ 异常"),
            "stopped": ("badge-secondary", "🖥️ 已停止"),
        }.get(st, ("badge-secondary", "🖥️ 未知"))
        return {
            "pw_status": st,
            "pw_badge_class": badge_cls,
            "pw_badge_text": badge_text,
            "pw_tabs_count": tabs,
        }
    except Exception:
        return {
            "pw_status": "stopped",
            "pw_badge_class": "badge-secondary",
            "pw_badge_text": "🖥️ 已停止",
            "pw_tabs_count": 0,
        }


# ─── API 端点 ─────────────────────────────────


@app.route("/api/browser/start", methods=["POST"])
@login_required
def api_browser_start():
    """启动 Playwright 浏览器"""
    engine = get_engine()
    ok = engine.start()
    status = engine.get_status()
    return jsonify({
        "success": ok,
        "status": status["status"],
        "badge_text": status["badge_text"],
        "error": status.get("error", ""),
    })


@app.route("/api/browser/stop", methods=["POST"])
@login_required
def api_browser_stop():
    """停止 Playwright 浏览器"""
    engine = get_engine()
    ok = engine.stop()
    status = engine.get_status()
    return jsonify({
        "success": ok,
        "status": status["status"],
        "badge_text": status["badge_text"],
    })


@app.route("/api/browser/restart", methods=["POST"])
@login_required
def api_browser_restart():
    """重启 Playwright 浏览器"""
    engine = get_engine()
    ok = engine.restart()
    status = engine.get_status()
    return jsonify({
        "success": ok,
        "status": status["status"],
        "badge_text": status["badge_text"],
        "error": status.get("error", ""),
    })


@app.route("/api/browser/status")
def api_browser_status():
    """获取浏览器引擎状态"""
    engine = get_engine()
    status = engine.get_status()
    return jsonify({
        "success": True,
        "data": status,
    })


@app.route("/api/browser/keepalive", methods=["POST"])
@login_required
def api_browser_keepalive():
    """标记活动（防止超时关闭）"""
    engine = get_engine()
    engine.keep_alive()
    return jsonify({"success": True})


@app.route("/api/browser/config", methods=["GET"])
@login_required
def api_browser_get_config():
    """获取当前 Playwright 配置"""
    engine = get_engine()
    cfg = engine.get_config()
    return jsonify({"success": True, "config": cfg})


@app.route("/api/browser/config", methods=["POST"])
@login_required
def api_browser_update_config():
    """更新 Playwright 配置"""
    data = request.get_json() or {}
    engine = get_engine()
    cfg = engine.update_config(data)
    return jsonify({"success": True, "config": cfg})


# ─── 设置页面 ─────────────────────────────────


@app.route("/playwright-settings")
@login_required
def playwright_settings_page():
    """Playwright 浏览器引擎配置页面"""
    engine = get_engine()
    status = engine.get_status()
    cfg = engine.get_config()
    return render_template(
        "playwright_settings.html",
        status=status,
        config=cfg,
    )
