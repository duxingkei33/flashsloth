"""FlashSloth 路由中心 — 应用工厂

所有路由模块在此注册，admin.py 仅作为入口点。
"""
import os, sys, json, random, string, hashlib, hmac, time, base64, re, threading
import sqlite3

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

from flashsloth.core.article import Article
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.deployer import get_deployer, list_deployers
from flashsloth.core.config import load_config
from flashsloth.core.storage import get_storage, list_storages, LocalStorage
from flashsloth.core.captcha_handler import get_handler, CaptchaProvider
from flashsloth.core.ai_provider import get_router, list_ai_providers, get_ai_provider, AIRequest
from flashsloth.core.database import get_db, _get_boot_credentials

# 共享 Flask 应用实例及组件
from flashsloth.routes._app import app, login_manager, User


def configure_app():
    """配置应用（过滤器、登录管理器、路由注册）"""
    # ─── Jinja2 自定义过滤器 ───
    @app.template_filter("split")
    def jinja_split(value, sep):
        return value.split(sep)

    @app.template_filter("from_json")
    def from_json_filter(val):
        if not val:
            return []
        try:
            return json.loads(val) if isinstance(val, str) else val
        except:
            return val

    @app.template_filter("split")
    def split_filter(val, sep=","):
        if not val:
            return []
        return val.split(sep)

    @app.template_filter("first")
    def first_filter(val):
        if not val:
            return ""
        return val[0] if isinstance(val, (list, tuple)) else val

    @app.template_filter("dict_get")
    def dict_get_filter(d, key, default=""):
        return d.get(key, default) if d else default

    # 初始化 login_manager（绑定到 app）
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        conn = get_db()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        return User(row) if row else None

    # ─── 导入所有路由模块（触发 @app.route 注册）───
    import flashsloth.routes.auth
    import flashsloth.routes.accounts
    import flashsloth.routes.posts
    import flashsloth.routes.ai
    import flashsloth.routes.captcha_browser
    import flashsloth.routes.signin
    import flashsloth.routes.storage_deploy
    import flashsloth.routes.forum
    import flashsloth.routes.browser_login
    import flashsloth.routes.platforms
    import flashsloth.routes.api_v1
    from flashsloth.routes.api_v1 import init_api_v1
    init_api_v1()
    import flashsloth.routes.comment_monitor  # 💬 评论监控路由
    import flashsloth.routes.api_v2  # 🚪 Gateway API v2
    import flashsloth.routes.exploration      # 🔍 探索数据管理
    import flashsloth.routes.xianyu_search    # 🐟 闲鱼搜索
    import flashsloth.routes.pipeline_ui      # 📋 内容流水线
    import flashsloth.routes.notifications   # 🔔 通知系统
    import flashsloth.routes.gateway         # 📡 通知网关
    import flashsloth.routes.price_monitor    # 💰 价格监控

    return app, login_manager, User