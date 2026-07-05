"""FlashSloth Auth Routes — 登录/注册/改密/设置/首页"""
import os, sys, json, random, string, hashlib, hmac, time, base64, re, threading

from flask import (render_template, request, redirect, url_for,
                   flash, jsonify, session, make_response)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3

from flashsloth.core.database import get_db
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.deployer import get_deployer, list_deployers
from flashsloth.core.config import load_config
from flashsloth.core.storage import get_storage, list_storages, LocalStorage
from flashsloth.core.captcha_handler import get_handler, CaptchaProvider
from flashsloth.core.ai_provider import (get_router, list_ai_providers,
                                          get_ai_provider, AIRequest)

from flashsloth.routes._app import app, login_manager, User



# ─── 验证码 ─────────────────────────────────────
def send_sms_code(phone: str, code: str) -> bool:
    """发送短信验证码（占位—接入实际 SMS 服务商）"""
    # ⚠️ 替换为实际 SMS API: 阿里云/腾讯云/Twilio
    print(f"[SMS] 发送验证码 {code} 到 {phone} — 需接入 SMS 服务商")
    # 开发模式下自动通过
    return True


# ─── 首页 ───────────────────────────────────────
@app.route("/")
@login_required
def index():
    conn = get_db()
    # 真实总数（不限 20 条）
    total_articles = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE user_id=?", (current_user.id,)
    ).fetchone()[0]
    total_published = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE user_id=? AND status='published'", (current_user.id,)
    ).fetchone()[0]
    total_accounts = conn.execute(
        "SELECT COUNT(*) FROM platform_accounts WHERE user_id=? AND is_active=1", (current_user.id,)
    ).fetchone()[0]
    posts = conn.execute(
        "SELECT * FROM articles WHERE user_id=? ORDER BY updated_at DESC LIMIT 50",
        (current_user.id,)
    ).fetchall()
    logs = conn.execute(
        "SELECT pl.*, pa.account_name FROM publish_log pl "
        "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
        "ORDER BY pl.created_at DESC LIMIT 20"
    ).fetchall()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? AND is_active=1",
        (current_user.id,)
    ).fetchall()

    # 每篇文章的发布记录（用于显示已发布到的平台）
    publish_map = {}
    for post in posts:
        pid = post["id"]
        plogs = conn.execute(
            "SELECT pl.*, pa.account_name, pa.platform FROM publish_log pl "
            "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
            "WHERE pl.article_id=? AND (pl.success=1 OR pl.status='draft') "
            "ORDER BY pl.created_at DESC",
            (pid,),
        ).fetchall()
        publish_map[pid] = [dict(l) for l in plogs]

    # 每篇文章的 deploy 状态（最新一次发布记录）
    deploy_status_map = {}
    for post in posts:
        pid = post["id"]
        latest = conn.execute(
            "SELECT deploy_status FROM publish_log WHERE article_id=? AND success=1 ORDER BY id DESC LIMIT 1",
            (pid,),
        ).fetchone()
        deploy_status_map[pid] = latest["deploy_status"] if latest else None
    pconfig = conn.execute(
        "SELECT * FROM provider_config WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (current_user.id,)
    ).fetchone()

    # 部署器配置（在关闭连接前）
    deployer_configs = conn.execute(
        "SELECT * FROM deployer_configs WHERE user_id=? AND is_active=1",
        (current_user.id,)
    ).fetchall()
    conn.close()

    # 所有可用 platform
    pub_list = list_publishers()

    # 按平台分组账号
    account_map = {}
    for a in accounts:
        account_map.setdefault(a["platform"], []).append(dict(a))

    # 部署器信息
    dep_list = list_deployers()
    deployer_map = {}
    for d in deployer_configs:
        deployer_map.setdefault(d["deployer_name"], []).append(dict(d))

    return render_template("index.html",
                         posts=posts, logs=logs,
                         publishers=pub_list,
                         account_map=account_map,
                         deployers=dep_list,
                         deployer_map=deployer_map,
                         publish_map=publish_map,
                         deploy_status_map=deploy_status_map,
                         provider=pconfig,
                         total_articles=total_articles,
                         total_published=total_published,
                         total_accounts=total_accounts,
                         now=datetime.now())


# ─── 登录 ───────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            login_user(User(user))
            conn = get_db()
            conn.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user["id"],))
            conn.commit()
            conn.close()
            flash("登录成功", "success")
            return redirect(url_for("index"))
        flash("用户名或密码错误", "error")
    return render_template("login.html")


# ─── 注册 ───────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        email = request.form.get("email", "").strip()

        if not username or not password:
            flash("用户名和密码不能为空", "error")
            return render_template("register.html")
        if password != confirm:
            flash("两次密码不一致", "error")
            return render_template("register.html")
        if len(password) < 6:
            flash("密码至少6位", "error")
            return render_template("register.html")

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                (username, generate_password_hash(password), email),
            )
            conn.commit()
            # 创建默认 Provider 配置
            uid = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]
            conn.execute(
                "INSERT INTO provider_config (user_id, provider_type) VALUES (?, 'markdown')",
                (uid,),
            )
            conn.commit()
            conn.close()
            flash("注册成功，请登录", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            conn.close()
            flash("用户名或邮箱已存在", "error")

    return render_template("register.html")


@app.route("/send_sms_code", methods=["POST"])
def send_sms():
    """发送短信验证码（注册/登录用）"""
    phone = request.json.get("phone", "")
    if not phone:
        return jsonify({"success": False, "error": "手机号不能为空"})
    code = str(random.randint(100000, 999999))
    conn = get_db()
    # 过期旧码
    conn.execute("UPDATE verify_codes SET used=1 WHERE target=? AND used=0", (phone,))
    conn.execute(
        "INSERT INTO verify_codes (target, code, action, expires_at) VALUES (?, ?, 'register', datetime('now', '+10 minutes'))",
        (phone, code),
    )
    conn.commit()
    conn.close()
    send_sms_code(phone, code)
    return jsonify({"success": True, "message": "验证码已发送（开发模式: " + code + "）"})


# ─── 2FA / 换绑 ─────────────────────────────────
@app.route("/verify-2fa")
def verify_2fa():
    token = request.args.get("token", "")
    return render_template("verify_2fa.html", token=token)


@app.route("/api/verify-2fa", methods=["POST"])
def api_verify_2fa():
    """验证两步验证码（占位）"""
    # 接入 TOTP / SMS 验证
    return jsonify({"success": True, "message": "2FA 验证通过（开发模式自动通过）"})


# ─── 改密 ───────────────────────────────────────
@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id=?", (current_user.id,)).fetchone()
        if not user or not check_password_hash(user["password_hash"], old):
            flash("原密码错误", "error")
            conn.close()
            return render_template("change_password.html")
        if new != confirm:
            flash("两次密码不一致", "error")
            conn.close()
            return render_template("change_password.html")
        if len(new) < 6:
            flash("密码至少6位", "error")
            conn.close()
            return render_template("change_password.html")
        conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                     (generate_password_hash(new), current_user.id))
        conn.commit()
        conn.close()
        flash("密码已修改", "success")
        return redirect(url_for("index"))
    return render_template("change_password.html")


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """忘记密码（通过邮箱/短信验证码重置）"""
    if request.method == "POST":
        username = request.form.get("username", "")
        phone = request.form.get("phone", "")
        sms_code = request.form.get("sms_code", "")
        new_pass = request.form.get("new_password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user:
            flash("用户不存在", "error")
            conn.close()
            return render_template("forgot_password.html")

        if phone and sms_code:
            valid = conn.execute(
                "SELECT * FROM verify_codes WHERE target=? AND code=? AND used=0 AND action='reset_password'",
                (phone, sms_code)
            ).fetchone()
            if not valid:
                flash("验证码错误或已过期", "error")
                conn.close()
                return render_template("forgot_password.html")
            conn.execute("UPDATE verify_codes SET used=1 WHERE id=?", (valid["id"],))
            conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                         (generate_password_hash(new_pass), user["id"]))
            conn.commit()
            conn.close()
            flash("密码已重置，请登录", "success")
            return redirect(url_for("login"))

        flash("请提供手机号和验证码", "error")
        conn.close()
    return render_template("forgot_password.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ─── Provider 设置 ──────────────────────────────
@app.route("/settings")
@login_required
def settings_page():
    """设置页面（GET）"""
    conn = get_db()
    pconfig = conn.execute(
        "SELECT * FROM provider_config WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (current_user.id,)
    ).fetchone()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=?",
        (current_user.id,)
    ).fetchall()
    conn.close()

    publishers = list_publishers()
    # 合并账号信息
    for p in publishers:
        p["accounts"] = [dict(a) for a in accounts if a["platform"] == p["name"]]
        p["enabled"] = len(p["accounts"]) > 0
        # 补充当前配置值
        for field in p["config_fields"]:
            field["value"] = ""
            field["missing"] = []

    pconfig = dict(pconfig) if pconfig else {}
    provider_cfg = {
        "type": pconfig.get("provider_type", "markdown"),
        "notion": json.loads(pconfig.get("config_json", "{}")) if pconfig.get("config_json") else {},
    }

    return render_template("settings.html",
                         config={
                             "provider": provider_cfg,
                             "publishers": {},
                             "builder": {"type": "mkdocs", "auto_deploy": True},
                         },
                         publishers=publishers)


@app.route("/settings/provider", methods=["POST"])
@login_required
def set_provider():
    ptype = request.form.get("provider_type", "markdown")
    conn = get_db()
    # 更新或创建
    existing = conn.execute(
        "SELECT id FROM provider_config WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (current_user.id,)
    ).fetchone()
    cfg = {}
    if ptype == "notion":
        cfg = {
            "token": request.form.get("notion_token", ""),
            "database_id": request.form.get("notion_db_id", ""),
        }
    if existing:
        conn.execute(
            "UPDATE provider_config SET provider_type=?, config_json=?, updated_at=datetime('now') WHERE id=?",
            (ptype, json.dumps(cfg), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO provider_config (user_id, provider_type, config_json) VALUES (?, ?, ?)",
            (current_user.id, ptype, json.dumps(cfg)),
        )
    conn.commit()
    conn.close()
    flash("Provider 已更新", "success")
    return redirect(url_for("index") + "#provider")
