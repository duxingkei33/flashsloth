"""
FlashSloth Admin — 商用级多平台内容发布后台
功能：注册/登录/验证码/改密 / Provider选择 / Publisher多账号 / 一键发布
"""
import os, sys, json, random, string, hashlib, hmac, time, base64, re, io, shutil, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, session, make_response)
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3

from flashsloth.core.article import Article
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.deployer import get_deployer, list_deployers
from flashsloth.core.config import load_config
from flashsloth.core.storage import get_storage, list_storages, LocalStorage
from flashsloth.core.captcha_handler import get_handler, CaptchaProvider
from flashsloth.core.ai_provider import (get_router, list_ai_providers,
                                          get_ai_provider, AIRequest)
# 导入插件触发注册
import flashsloth.plugins.publisher_wordpress  # noqa
import flashsloth.plugins.publisher_wechat     # noqa
import flashsloth.plugins.publisher_juejin     # noqa
import flashsloth.plugins.publisher_rss        # noqa
import flashsloth.plugins.publisher_zhihu      # noqa
import flashsloth.plugins.publisher_csdn       # noqa
import flashsloth.plugins.publisher_discuz     # noqa
import flashsloth.plugins.publisher_github_pages  # noqa
import flashsloth.plugins.deployer_github_pages  # noqa
import flashsloth.plugins.storage_alist        # noqa
import flashsloth.plugins.forum_reader          # noqa
import flashsloth.plugins.forum_signin           # noqa
# SDK 平台适配器（触发注册）
import flashsloth.sdk.adapters.mydigit           # noqa
import flashsloth.sdk.adapters.amobbs            # noqa
import flashsloth.sdk.adapters.csdn              # noqa
import flashsloth.sdk.adapters.notion            # noqa
import flashsloth.sdk.adapters.github_pages      # noqa
import flashsloth.sdk.adapters.giscus             # noqa

app = Flask(__name__)
app.secret_key = os.environ.get("FLASHSLOTH_SECRET") or os.urandom(64).hex()
app.config["DEBUG"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

# 首次启动生成的随机 admin 凭证（见 init_db）
_BOOT_CREDENTIALS = None

# 数据分离：可通过 FLASHSLOTH_DB_PATH 环境变量覆盖数据库路径
# 默认使用项目根目录的 flashsloth.db（向后兼容）
_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "flashsloth.db")
DB_PATH = os.environ.get("FLASHSLOTH_DB_PATH") or _DEFAULT_DB

# ─── 数据库 ─────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            is_admin INTEGER DEFAULT 0,
            twofa_type TEXT DEFAULT '',
            twofa_secret TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS provider_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider_type TEXT NOT NULL DEFAULT 'markdown',
            config_json TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS platform_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            config_json TEXT DEFAULT '{}',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            body TEXT,
            summary TEXT,
            tags TEXT,
            source TEXT DEFAULT 'manual',
            status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS publish_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            account_id INTEGER,
            platform TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            url TEXT,
            error TEXT,
            message TEXT DEFAULT '',
            status TEXT DEFAULT 'published',
            deploy_status TEXT DEFAULT 'pending',
            retracted_at TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS forum_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            forum_name TEXT,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            tid TEXT,
            fid TEXT,
            author TEXT,
            content TEXT,
            tags TEXT DEFAULT '[]',
            score INTEGER DEFAULT 0,
            summary TEXT,
            source TEXT DEFAULT 'keyword',
            is_read INTEGER DEFAULT 0,
            is_my_thread INTEGER DEFAULT 0,
            reply_author TEXT,
            reply_content TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS verify_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            code TEXT NOT NULL,
            action TEXT DEFAULT 'register',
            expires_at TEXT,
            used INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS deployer_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            deployer_name TEXT NOT NULL,
            display_name TEXT,
            config_json TEXT DEFAULT '{}',
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS deploy_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id INTEGER,
            deployer_name TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            url TEXT,
            error TEXT,
            message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # ── 兼容旧 DB — publish_log 追加列 ────────────
    try:
        conn.execute("ALTER TABLE publish_log ADD COLUMN message TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE publish_log ADD COLUMN status TEXT DEFAULT 'published'")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE publish_log ADD COLUMN deploy_status TEXT DEFAULT 'pending'")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE publish_log ADD COLUMN retracted_at TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE publish_log ADD COLUMN updated_at TEXT")
    except Exception:
        pass
    conn.commit()

    # ─── 签到调度表 ────────────────────────────────
    conn.execute("""CREATE TABLE IF NOT EXISTS signin_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL UNIQUE,
        time_start TEXT DEFAULT '08:00',
        time_end TEXT DEFAULT '08:00',
        enabled INTEGER DEFAULT 1,
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()

    # ─── 评论监控配置表 ────────────────────────────
    conn.execute("""CREATE TABLE IF NOT EXISTS comment_monitor_config (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL UNIQUE,
        enabled INTEGER DEFAULT 1,
        slot_morning TEXT DEFAULT '12:00-12:30',
        slot_afternoon TEXT DEFAULT '15:00-15:30',
        slot_evening TEXT DEFAULT '20:00-20:30',
        auto_reply INTEGER DEFAULT 0,
        reply_style TEXT DEFAULT 'friendly',
        reply_tone TEXT DEFAULT '热心帮助',
        max_replies_per_day INTEGER DEFAULT 3,
        notify_replies INTEGER DEFAULT 1,
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()

    # ─── 评论回复表 ────────────────────────────────
    conn.execute("""CREATE TABLE IF NOT EXISTS comment_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_id INTEGER NOT NULL,
        account_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        forum_name TEXT DEFAULT '',
        thread_tid TEXT NOT NULL,
        thread_title TEXT DEFAULT '',
        thread_url TEXT DEFAULT '',
        reply_author TEXT DEFAULT '',
        reply_content TEXT DEFAULT '',
        reply_time TEXT DEFAULT '',
        reply_pid TEXT DEFAULT '',
        is_read INTEGER DEFAULT 0,
        is_new INTEGER DEFAULT 1,
        source TEXT DEFAULT 'auto',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()
    # 兼容旧 DB — 追加列
    for col in ['reply_time', 'reply_pid', 'is_auto_replied']:
        try:
            conn.execute(f"ALTER TABLE comment_replies ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception:
            pass
    conn.commit()

    # ─── 自动回复日志表 ────────────────────────────
    conn.execute("""CREATE TABLE IF NOT EXISTS auto_reply_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reply_id INTEGER,
        article_id INTEGER,
        account_id INTEGER,
        platform TEXT DEFAULT '',
        thread_tid TEXT DEFAULT '',
        reply_content TEXT DEFAULT '',
        ai_model TEXT DEFAULT '',
        success INTEGER DEFAULT 0,
        error TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()

    # ─── 首次运行：自动生成随机 admin 账号 ───
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        import string as _string
        admin_user = "admin_" + "".join(random.choices(_string.ascii_lowercase + _string.digits, k=6))
        admin_pass = "".join(random.choices(_string.ascii_letters + _string.digits, k=16))
        pw_hash = generate_password_hash(admin_pass)
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (admin_user, pw_hash),
        )
        conn.commit()
        # 为 admin 创建默认 Provider 配置
        uid = conn.execute("SELECT id FROM users WHERE username=?", (admin_user,)).fetchone()["id"]
        conn.execute(
            "INSERT INTO provider_config (user_id, provider_type) VALUES (?, 'markdown')",
            (uid,),
        )
        conn.commit()
        global _BOOT_CREDENTIALS
        _BOOT_CREDENTIALS = (admin_user, admin_pass)
        # 同时写入文件，避免终端输出被缓冲吞掉
        cred_path = os.path.join(os.path.dirname(__file__), ".boot_credentials")
        with open(cred_path, "w") as f:
            f.write(f"username: {admin_user}\npassword: {admin_pass}\n")
        print(f"[FlashSloth] 首次启动凭证已写入 {cred_path}", flush=True)
    else:
        _BOOT_CREDENTIALS = None

    conn.close()

# ─── 验证码 ─────────────────────────────────────
def generate_captcha() -> tuple[str, str]:
    """生成数学验证码，返回(题目, 答案)"""
    a, b = random.randint(1, 9), random.randint(1, 9)
    op = random.choice(['+', '-', '*'])
    if op == '+':
        ans = a + b
    elif op == '-':
        a, b = max(a, b), min(a, b)
        ans = a - b
    else:
        a, b = min(a, 5), min(b, 5)
        ans = a * b
    question = f"{a} {op} {b} = ?"
    return question, str(ans)

def send_sms_code(phone: str, code: str) -> bool:
    """发送短信验证码（占位—接入实际 SMS 服务商）"""
    # ⚠️ 替换为实际 SMS API: 阿里云/腾讯云/Twilio
    print(f"[SMS] 发送验证码 {code} 到 {phone} — 需接入 SMS 服务商")
    # 开发模式下自动通过
    return True

def generate_token(uid: int, action: str = "auth") -> str:
    """生成一次性操作 token"""
    raw = f"{uid}:{action}:{time.time()}:{random.randint(1000,9999)}"
    return base64.urlsafe_b64encode(raw.encode()).decode()

# ─── 用户 ───────────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "请先登录"

class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"] or ""
        self.phone = row["phone"] or ""
        self.is_admin = row["is_admin"] or 0
        self.twofa_type = row["twofa_type"] or ""

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return User(row) if row else None

# ─── 自定义模板过滤器 ────────────────────────────
@app.template_filter("from_json")
def from_json_filter(val):
    if not val:
        return {}
    try:
        return json.loads(val)
    except:
        return {}

@app.template_filter("dict_get")
def dict_get_filter(d, key, default=""):
    return d.get(key, default) if d else default

# ─── 路由 ───────────────────────────────────────
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
        "SELECT pl.*, pa.account_name, a.title as article_title FROM publish_log pl "
        "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
        "LEFT JOIN articles a ON pl.article_id=a.id "
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
            "WHERE pl.article_id=? AND pl.success=1 "
            "ORDER BY pl.created_at DESC",
            (pid,),
        ).fetchall()
        publish_map[pid] = [dict(l) for l in plogs]

    # 每篇文章的 deploy 状态：只要有一个已发布记录是 deployed 就算已部署
    deploy_status_map = {}
    for post in posts:
        pid = post["id"]
        deployed_one = conn.execute(
            "SELECT id FROM publish_log WHERE article_id=? AND success=1 AND deploy_status='deployed' LIMIT 1",
            (pid,),
        ).fetchone()
        deploy_status_map[pid] = "deployed" if deployed_one else "pending"
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

# ─── 平台账号管理 ──────────────────────────────
@app.route("/accounts")
@login_required
def accounts():
    conn = get_db()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? ORDER BY platform, created_at",
        (current_user.id,)
    ).fetchall()
    conn.close()
    platforms = list_publishers()
    # 按平台分组
    grouped = {}
    for a in accounts:
        grouped.setdefault(a["platform"], []).append(dict(a))
    return render_template("accounts.html",
                         grouped=grouped,
                         platforms=platforms)

@app.route("/accounts/add", methods=["POST"])
@login_required
def add_account():
    platform = request.form.get("platform", "")
    name = request.form.get("account_name", "")
    if not platform or not name:
        flash("请填写平台和账号名", "error")
        return redirect(url_for("accounts"))

    # 收集该平台的所有配置字段
    cfg = {}
    for key in request.form:
        if key.startswith(f"cfg_"):
            cfg[key[4:]] = request.form[key]

    conn = get_db()
    conn.execute(
        "INSERT INTO platform_accounts (user_id, platform, account_name, config_json) VALUES (?, ?, ?, ?)",
        (current_user.id, platform, name, json.dumps(cfg)),
    )
    conn.commit()
    conn.close()
    flash(f"{platform} 账号已添加", "success")
    return redirect(url_for("accounts"))

@app.route("/accounts/edit/<int:aid>", methods=["GET", "POST"])
@login_required
def edit_account(aid):
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    if not acct:
        flash("账号不存在", "error")
        conn.close()
        return redirect(url_for("accounts"))

    if request.method == "POST":
        name = request.form.get("account_name", "")
        cfg = {}
        for key in request.form:
            if key.startswith("cfg_"):
                cfg[key[4:]] = request.form[key]
        conn.execute(
            "UPDATE platform_accounts SET account_name=?, config_json=?, is_active=? WHERE id=?",
            (name, json.dumps(cfg),
             1 if request.form.get("is_active") else 0, aid),
        )
        conn.commit()
        conn.close()
        flash("账号已更新", "success")
        return redirect(url_for("accounts"))

    conn.close()
    platforms = list_publishers()
    return render_template("account_edit.html",
                         account=dict(acct),
                         platforms=platforms)

@app.route("/accounts/delete/<int:aid>")
@login_required
def delete_account(aid):
    conn = get_db()
    conn.execute("DELETE FROM platform_accounts WHERE id=? AND user_id=?", (aid, current_user.id))
    conn.commit()
    conn.close()
    flash("账号已删除", "success")
    return redirect(url_for("accounts"))

# ─── 文章 CRUD ─────────────────────────────────
@app.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
    if request.method == "POST":
        conn = get_db()
        conn.execute(
            "INSERT INTO articles (user_id, title, body, summary, tags) VALUES (?, ?, ?, ?, ?)",
            (current_user.id,
             request.form.get("title", ""),
             request.form.get("body", ""),
             request.form.get("summary", ""),
             json.dumps([t.strip() for t in request.form.get("tags", "").split(",") if t.strip()])),
        )
        conn.commit()
        conn.close()
        flash("文章已保存", "success")
        return redirect(url_for("index"))
    return render_template("edit.html", post=None)

@app.route("/post/edit/<int:pid>", methods=["GET", "POST"])
@login_required
def edit_post(pid):
    conn = get_db()
    if request.method == "POST":
        conn.execute(
            "UPDATE articles SET title=?, body=?, summary=?, tags=?, updated_at=datetime('now') WHERE id=? AND user_id=?",
            (request.form.get("title", ""), request.form.get("body", ""),
             request.form.get("summary", ""),
             json.dumps([t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]),
             pid, current_user.id),
        )
        conn.commit()
        conn.close()
        flash("文章已更新", "success")
        return redirect(url_for("index"))

    post = conn.execute(
        "SELECT * FROM articles WHERE id=? AND user_id=?",
        (pid, current_user.id)
    ).fetchone()
    conn.close()
    if not post:
        flash("文章不存在", "error")
        return redirect(url_for("index"))
    return render_template("edit.html", post=post)

@app.route("/post/delete/<int:pid>")
@login_required
def delete_post(pid):
    conn = get_db()
    conn.execute("DELETE FROM articles WHERE id=? AND user_id=?", (pid, current_user.id))
    conn.commit()
    conn.close()
    flash("文章已删除", "success")
    return redirect(url_for("index"))


# ─── 批量操作 API ──────────────────────────────
@app.route("/api/articles/batch-delete", methods=["POST"])
@login_required
def batch_delete_articles():
    """批量删除文章"""
    ids = request.json.get("ids", [])
    if not ids:
        return jsonify({"success": False, "error": "请选择文章"})
    conn = get_db()
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"DELETE FROM articles WHERE id IN ({placeholders}) AND user_id=?",
        (*ids, current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "deleted": len(ids)})


@app.route("/api/articles/batch-publish", methods=["POST"])
@login_required
def batch_publish_articles():
    """批量发布文章到 GitHub Pages（账号 ID=2）"""
    ids = request.json.get("ids", [])
    if not ids:
        return jsonify({"success": False, "error": "请选择文章"})
    from flashsloth.core.article import Article
    results = []
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=2 AND user_id=?", (current_user.id,)
    ).fetchone()
    if not acct:
        conn.close()
        return jsonify({"success": False, "error": "未找到 GitHub Pages 发布账号"})
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    for pid in ids:
        post = conn.execute(
            "SELECT * FROM articles WHERE id=? AND user_id=?", (pid, current_user.id)
        ).fetchone()
        if not post:
            results.append({"id": pid, "success": False, "error": "文章不存在"})
            continue
        existing = conn.execute(
            "SELECT id FROM publish_log WHERE article_id=? AND account_id=? AND success=1",
            (pid, acct["id"])
        ).fetchone()
        if existing:
            results.append({"id": pid, "success": True, "message": "already_published"})
            continue
        try:
            publisher = get_publisher(acct["platform"], cfg)
            article = Article(
                title=post["title"], body=post["body"],
                summary=post["summary"],
                tags=json.loads(post["tags"]) if post["tags"] else [],
            )
            result = publisher.publish(article)
            publish_status = result.get("message", "published") if result["success"] else "failed"
            conn.execute(
                "INSERT OR REPLACE INTO publish_log (article_id, account_id, platform, success, url, error, message, status) VALUES (?,?,?,?,?,?,?,?)",
                (pid, acct["id"], acct["platform"],
                 1 if result["success"] else 0,
                 result.get("url", ""), result.get("error", ""),
                 result.get("message", ""), publish_status),
            )
            if result["success"]:
                conn.execute("UPDATE articles SET status='published', updated_at=datetime('now') WHERE id=?", (pid,))
            results.append({"id": pid, "success": result["success"], "message": result.get("message", "")})
        except Exception as e:
            results.append({"id": pid, "success": False, "error": str(e)})
    # 触发部署器
    if any(r["success"] for r in results):
        deployers = conn.execute(
            "SELECT * FROM deployer_configs WHERE user_id=? AND is_active=1", (current_user.id,)
        ).fetchall()
        for dep in deployers:
            dep_cfg = json.loads(dep["config_json"]) if dep["config_json"] else {}
            try:
                deployer = get_deployer(dep["deployer_name"], dep_cfg)
                dep_result = deployer.deploy()
                if dep_result.get("success"):
                    conn.execute(
                        "UPDATE publish_log SET deploy_status='deployed' WHERE article_id IN ({}) AND (deploy_status IS NULL OR deploy_status='pending')".format(
                            ",".join("?" for _ in ids)),
                        (*ids,),
                    )
            except Exception:
                pass
    conn.commit()
    conn.close()
    return jsonify({"success": True, "results": results, "published": len(ids)})


@app.route("/api/articles", methods=["GET"])
@login_required
def api_articles():
    """获取文章列表（JSON），用于前端 AJAX 和测试"""
    conn = get_db()
    posts = conn.execute(
        "SELECT * FROM articles WHERE user_id=? ORDER BY updated_at DESC LIMIT 100",
        (current_user.id,)
    ).fetchall()
    conn.close()
    articles = []
    for p in posts:
        articles.append({
            "id": p["id"],
            "title": p["title"],
            "status": p["status"],
            "tags": json.loads(p["tags"]) if p["tags"] else [],
            "source": p["source"],
            "summary": p["summary"],
            "created_at": p["created_at"],
            "updated_at": p["updated_at"],
        })
    return jsonify({"articles": articles})


@app.route("/api/articles/batch-retract", methods=["POST"])
@login_required
def batch_retract_articles():
    """批量撤回文章发布"""
    ids = request.json.get("ids", [])
    if not ids:
        return jsonify({"success": False, "error": "请选择文章"})
    conn = get_db()
    results = []
    for pid in ids:
        logs = conn.execute(
            "SELECT pl.*, a.title, a.body, a.tags FROM publish_log pl "
            "LEFT JOIN articles a ON pl.article_id=a.id "
            "WHERE pl.article_id=? AND pl.success=1 AND (a.user_id=? OR ?)",
            (pid, current_user.id, current_user.is_admin)
        ).fetchall()
        for log in logs:
            acct = conn.execute("SELECT * FROM platform_accounts WHERE id=?", (log["account_id"],)).fetchone()
            if not acct:
                continue
            cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
            try:
                publisher = get_publisher(acct["platform"], cfg)
                article = Article(
                    title=log["title"] or "", body=log["body"] or "",
                    summary="", tags=json.loads(log["tags"]) if log["tags"] else [],
                )
                r = publisher.retract(article, dict(log))
                if r.get("success"):
                    conn.execute("UPDATE publish_log SET retracted_at=datetime('now'), success=0 WHERE id=?", (log["id"],))
                    conn.execute("UPDATE articles SET status='draft', updated_at=datetime('now') WHERE id=?", (pid,))
                    results.append({"id": pid, "success": True})
                else:
                    results.append({"id": pid, "success": False, "error": r.get("error", "撤回失败")})
            except Exception as e:
                results.append({"id": pid, "success": False, "error": str(e)})
    conn.commit()
    conn.close()
    return jsonify({"success": True, "results": results})

# ─── 发布 ───────────────────────────────────────
# ─── Discuz! 验证码登录 API ─────────────────────
@app.route("/api/discuz/captcha", methods=["POST"])
@login_required
def discuz_get_captcha():
    """获取 Discuz! 验证码图片和 session 信息"""
    site_url = request.json.get("site_url", "").rstrip("/")
    if not site_url:
        return jsonify({"success": False, "error": "缺少论坛地址"})

    try:
        sess = requests.Session()
        sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 获取登录页
        r = sess.get(f"{site_url}/member.php?mod=logging&action=login", timeout=20)
        formhash = re.search(r'name="formhash"\s+value="([^"]+)"', r.text)
        form_action = re.search(
            r'<form[^>]*name="login"[^>]*action="([^"]*)"', r.text
        )
        seccode_span = re.search(r'id="seccode_([^"]+)"', r.text)
        if not formhash or not form_action or not seccode_span:
            return jsonify({"success": False, "error": "无法解析登录页面"})

        formhash = formhash.group(1)
        loginhash = re.search(r"loginhash=([a-zA-Z0-9]+)", form_action.group(1))
        loginhash = loginhash.group(1) if loginhash else ""
        seccodehash = seccode_span.group(1)

        # 刷新验证码（跳过第一个）
        import time as _time
        sess.get(
            f"{site_url}/misc.php?mod=seccode&action=update&idhash={seccodehash}&{_time.time()}",
            timeout=15,
        )
        _time.sleep(0.3)
        js = sess.get(
            f"{site_url}/misc.php?mod=seccode&action=update&idhash={seccodehash}&{_time.time()}",
            timeout=15,
        )
        upd = re.search(r"update=(\d+)", js.text)
        if not upd:
            return jsonify({"success": False, "error": "无法获取验证码"})
        upd = upd.group(1)

        # 下载验证码图片
        img = sess.get(
            f"{site_url}/misc.php?mod=seccode&update={upd}&idhash={seccodehash}",
            timeout=15,
            headers={
                "Accept": "image/*",
                "Referer": f"{site_url}/member.php?mod=logging&action=login",
            },
        )
        if len(img.content) < 100:
            return jsonify({"success": False, "error": "验证码图片获取失败"})

        # 保存图片和 session 信息到临时存储
        img_b64 = base64.b64encode(img.content).decode()
        token = generate_token(current_user.id, "discuz_captcha")
        # 存到 verify_codes 表（临时存 session 信息）
        conn = get_db()
        sess_data = json.dumps({
            "cookies": {c.name: c.value for c in sess.cookies},
            "seccodehash": seccodehash,
            "loginhash": loginhash,
            "formhash": formhash,
            "site_url": site_url,
        })
        conn.execute(
            "INSERT INTO verify_codes (target, code, action) VALUES (?, ?, 'discuz_session')",
            (f"user_{current_user.id}_{token}", sess_data),
        )
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "token": token,
            "image": f"data:image/png;base64,{img_b64}",
            "seccodehash": seccodehash,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"获取验证码异常: {e}"})


@app.route("/api/discuz/login", methods=["POST"])
@login_required
def discuz_login_with_captcha():
    """提交验证码完成 Discuz! 登录"""
    token = request.json.get("token", "")
    captcha = request.json.get("captcha", "").strip()
    if not token or not captcha:
        return jsonify({"success": False, "error": "缺少 token 或验证码"})

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM verify_codes WHERE target=? AND action='discuz_session' AND used=0",
        (f"user_{current_user.id}_{token}",),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "会话已过期，请重新获取验证码"})

    conn.execute("UPDATE verify_codes SET used=1 WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()

    sess_data = json.loads(row["code"])
    site_url = sess_data["site_url"]

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    for name, val in sess_data["cookies"].items():
        session.cookies.set(name, val, domain=site_url.replace("https://", "").replace("http://", ""))

    # 1. 验证验证码
    check_url = f"{site_url}/misc.php?mod=seccode&action=check&inajax=1"
    check_resp = session.post(
        check_url, data={"secverify": captcha, "idhash": sess_data["seccodehash"]}, timeout=10
    )
    if "succeed" not in check_resp.text:
        return jsonify({"success": False, "error": "验证码错误，请重新填写", "captcha_wrong": True})

    # 2. 登录（需要用户名密码，从请求中获取）
    username = request.json.get("username", "")
    password = request.json.get("password", "")

    login_url = (
        f"{site_url}/member.php?mod=logging&action=login"
        f"&loginsubmit=yes&loginhash={sess_data['loginhash']}"
    )
    login_data = {
        "formhash": sess_data["formhash"],
        "referer": site_url + "/",
        "loginfield": "username",
        "username": username,
        "password": password,
        "questionid": "0",
        "answer": "",
        "seccodehash": sess_data["seccodehash"],
        "seccodemodid": "member::logging",
        "seccodeverify": captcha,
        "cookietime": "2592000",
    }
    resp = session.post(login_url, data=login_data, timeout=20, allow_redirects=True)

    # 3. 检查结果
    auth = [c for c in session.cookies if "auth" in c.name.lower()]
    if auth:
        # 登录成功！返回完整 cookie 字符串
        cookie_str = "; ".join([f"{c.name}={c.value}" for c in session.cookies])
        return jsonify({
            "success": True,
            "message": "登录成功",
            "cookies": cookie_str,
        })

    # 提取错误信息
    err_text = "登录失败"
    for p in [
        r'<div[^>]*class="alert_error"[^>]*>([\s\S]*?)</div>',
        r'<p[^>]*class="alert_info"[^>]*>(.*?)</p>',
        r'<p[^>]*>(.*?)(?:</p>)',
    ]:
        m = re.search(p, resp.text, re.DOTALL)
        if m:
            t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if t and len(t) < 300:
                err_text = t
                break

    return jsonify({"success": False, "error": err_text})


# ─── 通用验证码处理 API ─────────────────────────


@app.route("/api/captcha/status/<int:aid>", methods=["GET"])
@login_required
def captcha_check_login(aid):
    """检查账号是否需要登录（发布前调用）"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    # 检查是否已有有效 cookie
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    cookie = cfg.get("cookie", "")
    if not cookie:
        return jsonify({"logged_in": False, "reason": "no_cookie", "needs_login": True})

    # 尝试用SDK adapter检查登录状态
    try:
        from sdk.adapter import get_adapter
        adapter = get_adapter(acct["platform"], cfg)
        if adapter and hasattr(adapter, "test_connection"):
            result = adapter.test_connection()
            if result.get("success"):
                return jsonify({"logged_in": True, "needs_login": False})
            return jsonify({
                "logged_in": False,
                "reason": "cookie_expired",
                "needs_login": True,
                "error": result.get("error", "Cookie 已过期"),
            })
    except Exception:
        pass

    return jsonify({"logged_in": True, "needs_login": False})


@app.route("/api/captcha/start/<int:aid>", methods=["POST"])
@login_required
def captcha_start_login(aid):
    """启动登录流程 — 获取验证码并返回 base64 图片"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    site_url = request.json.get("site_url", "") or (
        json.loads(acct["config_json"]).get("site_url", "") if acct["config_json"] else ""
    )
    platform = acct["platform"]

    # 根据平台类型执行不同的验证码获取逻辑
    import requests as _requests

    try:
        sess = _requests.Session()
        sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 访问登录页
        login_url = f"{site_url}/member.php?mod=logging&action=login"
        r = sess.get(login_url, timeout=20)

        formhash = re.search(r'name="formhash"\s+value="([^"]+)"', r.text)
        form_action = re.search(
            r'<form[^>]*name="login"[^>]*action="([^"]*)"', r.text
        )
        seccode_span = re.search(r'id="seccode_([^"]+)"', r.text)

        if not formhash or not form_action or not seccode_span:
            # 可能不需要验证码，尝试直接密码登录
            return jsonify({
                "success": True,
                "needs_captcha": False,
                "message": "该平台不需要验证码，可直接登录",
            })

        formhash = formhash.group(1)
        loginhash = re.search(r"loginhash=([a-zA-Z0-9]+)", form_action.group(1))
        loginhash = loginhash.group(1) if loginhash else ""
        seccodehash = seccode_span.group(1)

        # 刷新验证码
        sess.get(
            f"{site_url}/misc.php?mod=seccode&action=update&idhash={seccodehash}&{int(time.time())}",
            timeout=15,
        )
        time.sleep(0.3)
        js = sess.get(
            f"{site_url}/misc.php?mod=seccode&action=update&idhash={seccodehash}&{int(time.time())}",
            timeout=15,
        )
        upd = re.search(r"update=(\d+)", js.text)
        if not upd:
            return jsonify({"success": False, "error": "无法获取验证码图片"})
        upd = upd.group(1)

        # 下载验证码图片
        img = sess.get(
            f"{site_url}/misc.php?mod=seccode&update={upd}&idhash={seccodehash}",
            timeout=15,
            headers={"Accept": "image/*", "Referer": login_url},
        )
        if len(img.content) < 100:
            return jsonify({"success": False, "error": "验证码图片获取失败"})

        img_b64 = base64.b64encode(img.content).decode()

        # 生成 token 并存 session 信息
        token = hashlib.md5(f"{current_user.id}_{aid}_{time.time()}".encode()).hexdigest()[:16]

        conn = get_db()
        sess_data = json.dumps({
            "cookies": {c.name: c.value for c in sess.cookies},
            "seccodehash": seccodehash,
            "loginhash": loginhash,
            "formhash": formhash,
            "site_url": site_url,
            "account_id": aid,
            "username": json.loads(acct["config_json"]).get("username", "") if acct["config_json"] else "",
            "password": json.loads(acct["config_json"]).get("password", "") if acct["config_json"] else "",
        })
        conn.execute(
            "INSERT INTO verify_codes (target, code, action) VALUES (?, ?, 'captcha_session')",
            (f"user_{current_user.id}_{token}", sess_data),
        )
        conn.commit()
        conn.close()

        # 检查是否配置了自动接码
        captcha_provider = acct["captcha_provider"] if acct["captcha_provider"] else "manual"

        return jsonify({
            "success": True,
            "needs_captcha": True,
            "token": token,
            "image": f"data:image/png;base64,{img_b64}",
            "seccodehash": seccodehash,
            "attempt": 1,
            "max_attempts": 3,
            "captcha_provider": captcha_provider,
            "message": f"请输入验证码（第1次，最多3次）",
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"获取验证码异常: {e}"})


@app.route("/api/captcha/submit", methods=["POST"])
@login_required
def captcha_submit():
    """提交验证码 — 完成登录或返回新验证码"""
    token = request.json.get("token", "")
    captcha_code = request.json.get("captcha", "").strip()
    if not token or not captcha_code:
        return jsonify({"success": False, "error": "缺少 token 或验证码"})

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM verify_codes WHERE target=? AND action='captcha_session' AND used=0",
        (f"user_{current_user.id}_{token}",),
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "会话已过期，请重新获取验证码"})

    # 标记使用
    conn.execute("UPDATE verify_codes SET used=1 WHERE id=?", (row["id"],))
    conn.commit()

    sess_data = json.loads(row["code"])
    site_url = sess_data["site_url"]
    account_id = sess_data.get("account_id", 0)
    attempt = request.json.get("attempt", 1)
    max_attempts = request.json.get("max_attempts", 3)

    import requests as _requests
    session = _requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })
    for name, val in sess_data["cookies"].items():
        session.cookies.set(name, val, domain=site_url.replace("https://", "").replace("http://", ""))

    # 1. 验证验证码
    check_url = f"{site_url}/misc.php?mod=seccode&action=check&inajax=1"
    check_resp = session.post(
        check_url, data={"secverify": captcha_code, "idhash": sess_data["seccodehash"]}, timeout=10
    )
    if "succeed" not in check_resp.text:
        conn.close()
        # 验证码错误 → 是否需要新验证码？
        if attempt < max_attempts:
            return jsonify({
                "success": True,
                "logged_in": False,
                "new_challenge": True,
                "error": f"验证码错误（第{attempt}次），将获取新验证码",
                "attempt": attempt,
                "max_attempts": max_attempts,
            })
        return jsonify({
            "success": False,
            "error": f"验证码错误，已用尽{max_attempts}次机会",
            "attempt": attempt,
            "max_attempts": max_attempts,
        })

    # 2. 登录
    username = request.json.get("username") or sess_data.get("username", "")
    password = request.json.get("password") or sess_data.get("password", "")

    login_url = (
        f"{site_url}/member.php?mod=logging&action=login"
        f"&loginsubmit=yes&loginhash={sess_data['loginhash']}"
    )
    login_data = {
        "formhash": sess_data["formhash"],
        "referer": site_url + "/",
        "loginfield": "username",
        "username": username,
        "password": password,
        "questionid": "0",
        "answer": "",
        "seccodehash": sess_data["seccodehash"],
        "seccodemodid": "member::logging",
        "seccodeverify": captcha_code,
        "cookietime": "2592000",
    }
    resp = session.post(login_url, data=login_data, timeout=20, allow_redirects=True)

    # 3. 检查结果
    auth = [c for c in session.cookies if "auth" in c.name.lower()]
    if auth:
        # 登录成功
        cookie_str = "; ".join([f"{c.name}={c.value}" for c in session.cookies])

        # 更新账号配置中的 cookie
        if account_id:
            acct_row = conn.execute(
                "SELECT config_json FROM platform_accounts WHERE id=?", (account_id,)
            ).fetchone()
            if acct_row:
                cfg = json.loads(acct_row["config_json"]) if acct_row["config_json"] else {}
                cfg["cookie"] = cookie_str
                conn.execute(
                    "UPDATE platform_accounts SET config_json=? WHERE id=?",
                    (json.dumps(cfg), account_id),
                )
                conn.commit()

        conn.close()
        return jsonify({
            "success": True,
            "logged_in": True,
            "message": "登录成功 ✅",
            "cookies": cookie_str,
            "attempt": attempt,
            "max_attempts": max_attempts,
        })

    conn.close()

    # 提取错误信息
    err_text = "登录失败"
    for p in [
        r'<div[^>]*class="alert_error"[^>]*>([\s\S]*?)</div>',
        r'<p[^>]*class="alert_info"[^>]*>(.*?)</p>',
    ]:
        m = re.search(p, resp.text, re.DOTALL)
        if m:
            t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if t and len(t) < 300:
                err_text = t
                break

    # 检查是否又出现验证码（第二次验证码）
    new_seccode = re.search(r'id="seccode_([^"]+)"', resp.text)
    if new_seccode and attempt < max_attempts:
        next_attempt = attempt + 1
        # 获取新验证码
        new_hash = new_seccode.group(1)
        session.get(
            f"{site_url}/misc.php?mod=seccode&action=update&idhash={new_hash}&{int(time.time())}",
            timeout=15,
        )
        time.sleep(0.3)
        js = session.get(
            f"{site_url}/misc.php?mod=seccode&action=update&idhash={new_hash}&{int(time.time())}",
            timeout=15,
        )
        upd = re.search(r"update=(\d+)", js.text)
        if upd:
            img = session.get(
                f"{site_url}/misc.php?mod=seccode&update={upd.group(1)}&idhash={new_hash}",
                timeout=15,
                headers={"Accept": "image/*"},
            )
            if len(img.content) >= 100:
                new_img_b64 = base64.b64encode(img.content).decode()

                # 存储新的session
                new_sess_data = dict(sess_data)
                new_sess_data["cookies"] = {c.name: c.value for c in session.cookies}
                new_sess_data["seccodehash"] = new_hash
                new_token = hashlib.md5(f"{current_user.id}_{account_id}_{time.time()}".encode()).hexdigest()[:16]

                conn = get_db()
                conn.execute(
                    "INSERT INTO verify_codes (target, code, action) VALUES (?, ?, 'captcha_session')",
                    (f"user_{current_user.id}_{new_token}", json.dumps(new_sess_data)),
                )
                conn.commit()
                conn.close()

                return jsonify({
                    "success": True,
                    "logged_in": False,
                    "new_challenge": True,
                    "token": new_token,
                    "image": f"data:image/png;base64,{new_img_b64}",
                    "seccodehash": new_hash,
                    "error": f"验证码通过，但仍需第二次验证码（第{next_attempt}次）",
                    "attempt": next_attempt,
                    "max_attempts": max_attempts,
                })

    return jsonify({
        "success": False,
        "error": err_text,
        "attempt": attempt,
        "max_attempts": max_attempts,
    })


@app.route("/api/captcha/provider/<int:aid>", methods=["GET", "POST"])
@login_required
def captcha_provider_config(aid):
    """获取/更新账号的验证码处理配置"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()

    if not acct:
        conn.close()
        return jsonify({"success": False, "error": "账号不存在"})

    if request.method == "GET":
        return jsonify({
            "success": True,
            "provider": acct["captcha_provider"] or "manual",
            "config": json.loads(acct["captcha_config"]) if acct.get("captcha_config") else {},
        })

    # POST: 更新
    data = request.json
    provider = data.get("provider", "manual")
    config = data.get("config", {})

    conn.execute(
        "UPDATE platform_accounts SET captcha_provider=?, captcha_config=? WHERE id=?",
        (provider, json.dumps(config), aid),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "验证码配置已更新"})


@app.route("/api/captcha/list")
@login_required
def captcha_list_available():
    """列出可用的验证码处理方式"""
    return jsonify({
        "success": True,
        "providers": [
            {"value": "manual", "label": "手动输入（弹窗）", "description": "在后台弹出验证码图片，手动输入"},
            {"value": "ttshitu", "label": "图鉴自动识别", "description": "通过 ttshitu.com API 自动识别验证码（需配置密钥）"},
            {"value": "2captcha", "label": "2captcha", "description": "通过 2captcha.com API 自动识别验证码（需配置密钥）"},
        ],
    })


# ─── AI 能力配置 API ────────────────────────────


@app.route("/api/ai/providers")
@login_required
def ai_list_providers():
    """列出所有AI Provider及其能力"""
    providers = list_ai_providers()
    return jsonify({"success": True, "providers": providers})


@app.route("/api/ai/config")
@login_required
def ai_get_config():
    """获取AI能力路由配置"""
    router = get_router()
    return jsonify({
        "success": True,
        "capabilities": {k: v for k, v in router._capability_configs.items()},
        "providers": router._provider_configs,
    })


@app.route("/api/ai/config", methods=["POST"])
@login_required
def ai_update_config():
    """更新AI能力路由配置"""
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "缺少配置数据"})

    router = get_router()
    if "capabilities" in data:
        for cap, cfg in data["capabilities"].items():
            router.set_capability_config(cap, cfg)
    if "providers" in data:
        for provider, cfg in data["providers"].items():
            router.set_provider_config(provider, cfg)
    router.save_config()

    return jsonify({"success": True, "message": "AI配置已更新"})


@app.route("/api/ai/generate", methods=["POST"])
@login_required
def ai_generate():
    """调用AI生成内容"""
    data = request.json
    capability = data.get("capability", "writing")
    prompt = data.get("prompt", "")

    if not prompt:
        return jsonify({"success": False, "error": "缺少提示词"})

    router = get_router()
    result = router.call(
        capability=capability,
        prompt=prompt,
        temperature=data.get("temperature", 0.7),
        max_tokens=data.get("max_tokens", 4096),
        model=data.get("model", ""),
    )

    return jsonify({
        "success": result.success,
        "content": result.content,
        "images": result.images,
        "audio": result.audio,
        "model": result.model,
        "provider": result.provider,
        "error": result.error,
    })


@app.route("/api/ai/generate/parallel", methods=["POST"])
@login_required
def ai_generate_parallel():
    """并行调用AI（适合批量画图）"""
    data = request.json
    capability = data.get("capability", "image_gen")
    prompts = data.get("prompts", [])

    if not prompts:
        return jsonify({"success": False, "error": "缺少prompts列表"})

    router = get_router()
    results = router.call_parallel(capability=capability, prompts=prompts)

    return jsonify({
        "success": True,
        "results": [
            {
                "success": r.success,
                "content": r.content,
                "images": r.images,
                "audio": r.audio,
                "provider": r.provider,
                "model": r.model,
                "error": r.error,
            }
            for r in results
        ],
    })


@app.route("/ai/settings")
@login_required
def ai_settings_page():
    """AI配置管理页面"""
    router = get_router()
    providers = list_ai_providers()
    config = {
        "capabilities": router._capability_configs,
        "providers": router._provider_configs,
    }
    return render_template("ai_settings.html",
                         providers=providers,
                         config=config)


@app.route("/api/accounts/test/<int:aid>", methods=["POST"])
@login_required
def test_account(aid):
    """测试指定账号的连接状态"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    try:
        publisher = get_publisher(acct["platform"], cfg)
        if hasattr(publisher, "test_connection"):
            result = publisher.test_connection()
            return jsonify(result)
        return jsonify({"success": False, "error": "该平台不支持连接测试"})
    except Exception as e:
        return jsonify({"success": False, "error": f"测试异常: {e}"})


# ─── 存储管理 ──────────────────────────────────
STORAGE_DB_TYPE = "storage_config"


@app.route("/storage/settings")
@login_required
def storage_settings():
    """存储设置页面"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
        (current_user.id, STORAGE_DB_TYPE),
    ).fetchone()
    conn.close()

    current_cfg = json.loads(row["config_json"]) if row else {}
    storages = list_storages()
    return render_template("storage_settings.html",
                         storages=storages,
                         current=current_cfg,
                         enabled=bool(current_cfg.get("backend")))


@app.route("/api/storage/save", methods=["POST"])
@login_required
def storage_save():
    """保存存储配置"""
    backend = request.json.get("backend", "")
    config = request.json.get("config", {})

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
        (current_user.id, STORAGE_DB_TYPE),
    ).fetchone()

    payload = json.dumps({"backend": backend, **config})
    if existing:
        conn.execute(
            "UPDATE provider_config SET config_json=?, updated_at=datetime('now') WHERE id=?",
            (payload, existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO provider_config (user_id, provider_type, config_json) VALUES (?, ?, ?)",
            (current_user.id, STORAGE_DB_TYPE, payload),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "存储配置已保存"})


@app.route("/api/storage/test", methods=["POST"])
@login_required
def storage_test():
    """测试存储连接"""
    backend = request.json.get("backend", "local")
    config = request.json.get("config", {})
    try:
        storage = get_storage(backend, config)
        result = storage.test_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/storage/list", methods=["POST"])
@login_required
def storage_list():
    """列文件目录"""
    path = request.json.get("path", "/")
    try:
        storage = _get_active_storage()
        if not storage:
            return jsonify({"success": False, "error": "未配置存储"})
        items = storage.list(path)
        return jsonify({"success": True, "items": items, "path": path})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/storage/upload", methods=["POST"])
@login_required
def storage_upload():
    """上传文件到存储"""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未选择文件"})

    file = request.files["file"]
    article_id = request.form.get("article_id", type=int)
    remote_path = request.form.get("path", "")

    try:
        storage = _get_active_storage()
        if not storage:
            return jsonify({"success": False, "error": "未配置存储"})

        file_data = file.read()
        filename = file.filename

        if remote_path:
            # 上传到指定路径
            result = storage.upload_bytes(file_data, remote_path)
        elif article_id:
            # 上传为文章附件
            result = storage.upload_article_attachment_bytes(file_data, article_id, filename)
        else:
            # 按类型自动归类
            cat = storage.ensure_category_dir("resource")
            remote = f"/resource/{filename}"
            result = storage.upload_bytes(file_data, storage.full_path(remote))

        return jsonify({
            "success": True,
            "path": result.get("path", ""),
            "size": result.get("size", 0),
            "url": storage.get_url(result.get("path", "")),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/storage/mkdir", methods=["POST"])
@login_required
def storage_mkdir():
    """创建目录"""
    path = request.json.get("path", "")
    if not path:
        return jsonify({"success": False, "error": "缺少路径"})
    try:
        storage = _get_active_storage()
        if not storage:
            return jsonify({"success": False, "error": "未配置存储"})
        storage.mkdir(storage.full_path(path))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/storage/delete", methods=["POST"])
@login_required
def storage_delete():
    """删除文件/目录"""
    path = request.json.get("path", "")
    if not path:
        return jsonify({"success": False, "error": "缺少路径"})
    try:
        storage = _get_active_storage()
        if not storage:
            return jsonify({"success": False, "error": "未配置存储"})
        storage.delete(storage.full_path(path))
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def _get_active_storage():
    """获取当前用户配置的存储后端"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
        (current_user.id, STORAGE_DB_TYPE),
    ).fetchone()
    conn.close()

    if not row:
        return None

    cfg = json.loads(row["config_json"]) if row["config_json"] else {}
    backend = cfg.pop("backend", "local")
    try:
        return get_storage(backend, cfg)
    except Exception:
        return None


@app.route("/publish", methods=["POST"])
@login_required
def publish():
    """从文章列表选择发布：选择文章 + 选择平台账号"""
    article_id = request.form.get("article_id", type=int)
    account_ids = request.form.getlist("account_ids")

    if not article_id or not account_ids:
        flash("请选择文章和发布目标", "error")
        return redirect(url_for("index"))

    conn = get_db()
    post = conn.execute(
        "SELECT * FROM articles WHERE id=? AND user_id=?",
        (article_id, current_user.id)
    ).fetchone()
    if not post:
        flash("文章不存在", "error")
        conn.close()
        return redirect(url_for("index"))

    article = Article(
        title=post["title"],
        body=post["body"],
        summary=post["summary"],
        tags=json.loads(post["tags"]) if post["tags"] else [],
    )

    results = []
    for aid in account_ids:
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
            (aid, current_user.id)
        ).fetchone()
        if not acct:
            continue

        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        # 检查是否有发布时选择的板块（Discuz 等论坛）
        forum_fid = request.form.get(f"forum_fid_{aid}")
        if forum_fid:
            cfg["fid"] = forum_fid

        # 去重：检查是否已发布到该账号
        existing = conn.execute(
            "SELECT id FROM publish_log WHERE article_id=? AND account_id=? AND success=1",
            (article_id, aid)
        ).fetchone()
        if existing:
            results.append({"success": True, "error": "", "message": "already_published"})
            continue

        try:
            publisher = get_publisher(acct["platform"], cfg)
            result = publisher.publish(article)
            publish_status = result.get("message", "published") if result["success"] else "failed"
            conn.execute(
                "INSERT OR REPLACE INTO publish_log (article_id, account_id, platform, success, url, error, message, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (article_id, aid, acct["platform"],
                 1 if result["success"] else 0,
                 result.get("url", ""), result.get("error", ""),
                 result.get("message", ""), publish_status),
            )
            results.append(result)
        except Exception as e:
            conn.execute(
                "INSERT OR REPLACE INTO publish_log (article_id, account_id, platform, success, error) VALUES (?, ?, ?, 0, ?)",
                (article_id, aid, acct["platform"], str(e)),
            )
            results.append({"success": False, "error": str(e)})

    if any(r["success"] for r in results):
        conn.execute("UPDATE articles SET status='published', updated_at=datetime('now') WHERE id=?", (article_id,))

    conn.commit()

    # ── 自动部署：发布成功后自动触发所有活跃部署器 ──
    if any(r["success"] for r in results):
        deployers = conn.execute(
            "SELECT * FROM deployer_configs WHERE user_id=? AND is_active=1",
            (current_user.id,)
        ).fetchall()
        for dep in deployers:
            cfg = json.loads(dep["config_json"]) if dep["config_json"] else {}
            try:
                deployer = get_deployer(dep["deployer_name"], cfg)
                result = deployer.deploy()
                if result.get("success"):
                    conn.execute(
                        "UPDATE publish_log SET deploy_status='deployed' WHERE article_id=? AND (deploy_status IS NULL OR deploy_status='pending')",
                        (article_id,),
                    )
                    if dep["deployer_name"] == "github_pages":
                        flash("⏳ GitHub Pages 需要 1-2 分钟刷新，请稍后查看", "info")
            except Exception:
                pass  # 部署失败不阻塞发布结果
        conn.commit()

    conn.close()

    success_count = sum(1 for r in results if r["success"])
    already_published = sum(1 for r in results if r.get("message") == "already_published")
    pending_count = sum(1 for r in results if r.get("message") == "pending_review")
    parts = []
    if success_count:
        parts.append(f"{success_count} 成功")
    if already_published:
        parts.append(f"{already_published} 已发布跳过")
    if pending_count:
        parts.append(f"{pending_count} 待审核")
    failed = len(results) - success_count - already_published
    if failed:
        parts.append(f"{failed} 失败")
    flash(f"发布完成: {'; '.join(parts)}", "success" if success_count else "error")
    return redirect(url_for("index"))

# ─── 批量发布页面 ──────────────────────────────
@app.route("/publish/select/<int:pid>")
@login_required
def publish_select(pid):
    conn = get_db()
    post = conn.execute(
        "SELECT * FROM articles WHERE id=? AND user_id=?",
        (pid, current_user.id)
    ).fetchone()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? AND is_active=1",
        (current_user.id,)
    ).fetchall()
    # 获取该文章已发布的记录
    published = conn.execute(
        "SELECT pl.*, pa.account_name, pa.platform FROM publish_log pl "
        "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
        "WHERE pl.article_id=? AND pl.success=1 "
        "ORDER BY pl.created_at DESC",
        (pid,),
    ).fetchall()
    conn.close()

    if not post:
        flash("文章不存在", "error")
        return redirect(url_for("index"))

    return render_template("publish_select.html",
                         post=post, accounts=accounts,
                         published=[dict(p) for p in published])


# ─── 撤回 / 重新发布 ──────────────────────────
@app.route("/publish/retract/<int:log_id>")
@login_required
def publish_retract(log_id):
    """撤回已发布的文章"""
    conn = get_db()
    log = conn.execute(
        "SELECT pl.*, a.title, a.body, a.tags FROM publish_log pl "
        "LEFT JOIN articles a ON pl.article_id=a.id "
        "WHERE pl.id=? AND (a.user_id=? OR ?)",
        (log_id, current_user.id, current_user.is_admin)
    ).fetchone()
    if not log:
        conn.close()
        flash("发布记录不存在", "error")
        return redirect(url_for("index"))

    # 获取 publisher 并执行撤回
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=?",
        (log["account_id"],)
    ).fetchone()
    conn.close()

    if not acct:
        flash("关联账号不存在", "error")
        return redirect(url_for("index"))

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    try:
        publisher = get_publisher(acct["platform"], cfg)
        article = Article(
            title=log["title"] or "",
            body=log["body"] or "",
            tags=json.loads(log["tags"]) if log["tags"] else [],
        )
        log_dict = dict(log)
        result = publisher.retract(article, log_dict)

        if result.get("success"):
            # 更新发布日志状态（含部署状态）
            deploy_update = ", deploy_status='retracted'" if acct["platform"] in ("github_pages_blog",) else ""
            conn2 = get_db()
            conn2.execute(
                f"UPDATE publish_log SET status=?, retracted_at=datetime('now'){deploy_update} WHERE id=?",
                ("retracted", log_id),
            )
            # 同步更新文章状态为 draft
            if log.get("article_id"):
                conn2.execute(
                    "UPDATE articles SET status='draft', updated_at=datetime('now') WHERE id=?",
                    (log["article_id"],),
                )
            conn2.close()
            flash(f"✅ 撤回成功: {result.get('message', '')}", "success")
            # 如果是 GitHub Pages，自动部署（hugo rebuild + git push）
            if acct["platform"] == "github_pages_blog":
                try:
                    blog_dir = os.path.dirname(os.path.dirname(cfg.get("posts_dir", "")))
                    if blog_dir and os.path.isdir(blog_dir):
                        # 1. Hugo rebuild
                        import subprocess
                        hugo_bin = "/opt/data/bin/hugo"
                        if os.path.isfile(hugo_bin):
                            hugo_result = subprocess.run(
                                [hugo_bin], cwd=blog_dir,
                                capture_output=True, text=True, timeout=60
                            )
                            if hugo_result.returncode != 0:
                                flash(f"⚠️ Hugo构建失败: {hugo_result.stderr[:200]}", "warning")
                        # 2. Git commit + push (用deployer配置的repo_dir)
                        deploy_row = conn2.execute(
                            "SELECT config_json FROM deployer_configs WHERE deployer_name='github_pages' LIMIT 1"
                        ).fetchone()
                        if deploy_row:
                            dep_cfg = json.loads(deploy_row["config_json"])
                            repo_dir = dep_cfg.get("repo_dir", "")
                            token = dep_cfg.get("github_token", "")
                            username = dep_cfg.get("github_username", "")
                            if repo_dir and token and os.path.isdir(repo_dir):
                                auth_url = f"https://{username}:{token}@github.com/{username}/{username}.github.io.git"
                                cmds = [
                                    ["git", "-C", repo_dir, "add", "-A"],
                                ]
                                for cmd in cmds:
                                    subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                                ts = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')
                                subprocess.run(
                                    ["git", "-C", repo_dir, "commit", "-m", f"retract: auto-sync @ {ts}"],
                                    capture_output=True, text=True, timeout=30
                                )
                                # 先保存原remote，临时换带token的
                                old_remote = subprocess.run(
                                    ["git", "-C", repo_dir, "remote", "get-url", "origin"],
                                    capture_output=True, text=True, timeout=10
                                ).stdout.strip()
                                subprocess.run(
                                    ["git", "-C", repo_dir, "remote", "set-url", "origin", auth_url],
                                    capture_output=True, text=True, timeout=10
                                )
                                push_result = subprocess.run(
                                    ["git", "-C", repo_dir, "push", "origin", dep_cfg.get("branch", "main")],
                                    capture_output=True, text=True, timeout=30
                                )
                                # 恢复remote
                                subprocess.run(
                                    ["git", "-C", repo_dir, "remote", "set-url", "origin", old_remote],
                                    capture_output=True, text=True, timeout=10
                                )
                                if push_result.returncode == 0:
                                    flash("✅ 撤回内容已自动部署到 GitHub Pages，1-2分钟生效", "success")
                                else:
                                    flash(f"⚠️ 推送失败: {push_result.stderr[:200]}", "warning")
                except Exception as e:
                    flash(f"⚠️ 自动部署异常: {e}", "warning")
        else:
            flash(f"❌ 撤回失败: {result.get('error', '未知错误')}", "error")
    except Exception as e:
        flash(f"❌ 撤回异常: {e}", "error")

    return redirect(url_for("publish_manage"))


@app.route("/publish/re-publish/<int:log_id>")
@login_required
def publish_republish(log_id):
    """重新发布已撤回的文章"""
    conn = get_db()
    log = conn.execute(
        "SELECT * FROM publish_log WHERE id=?",
        (log_id,)
    ).fetchone()
    if not log:
        conn.close()
        flash("发布记录不存在", "error")
        return redirect(url_for("index"))

    # 重置发布日志状态
    conn.execute(
        "UPDATE publish_log SET status='published', retracted_at=NULL, created_at=datetime('now') WHERE id=?",
        (log_id,),
    )
    conn.commit()
    conn.close()

    flash("✅ 已标记为重新发布，请手动执行发布操作", "success")
    return redirect(url_for("publish_manage"))


# ─── 发布管理 ──────────────────────────────────
@app.route("/publish/manage")
@login_required
def publish_manage():
    """发布管理页面 — 查看所有发布状态，支持撤回"""
    conn = get_db()

    # 所有发布记录（含撤回的）
    logs = conn.execute(
        "SELECT pl.*, pa.account_name, pa.platform, a.title as article_title "
        "FROM publish_log pl "
        "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
        "LEFT JOIN articles a ON pl.article_id=a.id "
        "WHERE a.user_id=? OR ? "
        "ORDER BY pl.created_at DESC LIMIT 50",
        (current_user.id, current_user.is_admin)
    ).fetchall()

    # 按文章分组统计
    articles_raw = conn.execute(
        "SELECT a.*, "
        "(SELECT COUNT(*) FROM publish_log pl WHERE pl.article_id=a.id AND pl.success=1 AND (pl.status='published' OR pl.status IS NULL)) as pub_count, "
        "(SELECT COUNT(*) FROM publish_log pl WHERE pl.article_id=a.id AND pl.status='retracted') as ret_count "
        "FROM articles a WHERE a.user_id=? ORDER BY a.updated_at DESC",
        (current_user.id,)
    ).fetchall()

    # 给每篇文章附上已发布的 URL 列表
    articles = []
    for a in articles_raw:
        a = dict(a)
        pub_urls = conn.execute(
            "SELECT pl.platform, pl.url, pa.account_name, pl.deploy_status FROM publish_log pl "
            "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
            "WHERE pl.article_id=? AND pl.success=1 AND (pl.status='published' OR pl.status IS NULL) "
            "ORDER BY pl.created_at DESC",
            (a['id'],)
        ).fetchall()
        a['published_urls'] = [dict(u) for u in pub_urls]
        articles.append(a)

    conn.close()

    return render_template("publish_manage.html",
                         logs=[dict(l) for l in logs],
                         articles=[dict(a) for a in articles])

# ─── 检查待审核帖子状态 ────────────────────────────
@app.route("/api/publish/check-pending")
@login_required
def api_check_pending():
    """检查所有待审核帖子的实际状态，更新 DB 并返回结果"""
    conn = get_db()

    pending_logs = conn.execute(
        "SELECT pl.*, pa.platform, pa.config_json, pa.account_name "
        "FROM publish_log pl "
        "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
        "WHERE pl.status='pending_review' AND pl.success=1 "
        "AND (pa.user_id=? OR ?) "
        "ORDER BY pl.created_at DESC",
        (current_user.id, current_user.is_admin)
    ).fetchall()

    if not pending_logs:
        conn.close()
        return jsonify({"ok": True, "checked": 0, "updated": 0, "details": []})

    results = []
    updated_count = 0

    for log in pending_logs:
        log = dict(log)
        tid = None
        platform = log.get("platform", "")

        # 从 URL 提取帖子 ID
        if log.get("url"):
            # 支持 thread-N-1-1.html 和 tid=N 两种格式
            m = re.search(r'thread[=\-/]?(\d+)|[?&]tid=(\d+)', log["url"])
            if m:
                tid = m.group(1) or m.group(2)
        if not tid and log.get("id"):
            tid = str(log["id"])

        result = {
            "log_id": log["id"],
            "platform": platform,
            "account": log.get("account_name", ""),
            "url": log.get("url", ""),
            "tid": tid,
            "old_status": "pending_review",
            "new_status": "pending_review",
            "updated": False,
        }

        if platform == "discuz" and tid:
            cfg_str = log.get("config_json", "{}")
            cfg = json.loads(cfg_str) if cfg_str else {}
            if not cfg:
                result["error"] = "无法获取账号配置"
                results.append(result)
                continue

            try:
                publisher = get_publisher("discuz", cfg)
                verify = publisher._verify_thread_exists(tid)
                if verify["status"] == "published":
                    conn.execute(
                        "UPDATE publish_log SET status='published', message='published' WHERE id=?",
                        (log["id"],)
                    )
                    result["new_status"] = "published"
                    result["updated"] = True
                    result["title"] = verify.get("title", "")
                    result["url"] = verify.get("url", log.get("url", ""))
                    updated_count += 1
                else:
                    result["error"] = verify.get("title", "仍为待审核状态")
            except Exception as e:
                result["error"] = f"检查异常: {e}"
        else:
            result["error"] = f"平台 {platform} 暂不支持自动检查"

        results.append(result)

    conn.commit()
    conn.close()
    return jsonify({
        "ok": True,
        "checked": len(results),
        "updated": updated_count,
        "details": results,
    })


# ─── 部署管理 ──────────────────────────────────
@app.route("/deployers")
@login_required
def deployers_page():
    """部署配置管理页"""
    conn = get_db()
    configs = conn.execute(
        "SELECT * FROM deployer_configs WHERE user_id=? ORDER BY created_at DESC",
        (current_user.id,)
    ).fetchall()
    logs = conn.execute(
        "SELECT * FROM deploy_log ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()

    deployer_list = list_deployers()
    return render_template("deployers.html",
                         deployers=deployer_list,
                         configs=configs,
                         logs=logs)


@app.route("/deployers/add", methods=["POST"])
@login_required
def deployer_add():
    """添加部署配置"""
    deployer_name = request.form.get("deployer_name", "")
    display_name = request.form.get("display_name", "")
    if not deployer_name:
        flash("请选择部署器类型", "error")
        return redirect(url_for("deployers_page"))

    # 收集配置
    dl = list_deployers()
    cfg = {}
    for d in dl:
        if d["name"] == deployer_name:
            display_name = display_name or d["display_name"]
            for field in d["config_fields"]:
                val = request.form.get(f"cfg_{field['key']}", "")
                if val:
                    cfg[field["key"]] = val
            break

    conn = get_db()
    conn.execute(
        "INSERT INTO deployer_configs (user_id, deployer_name, display_name, config_json) VALUES (?, ?, ?, ?)",
        (current_user.id, deployer_name, display_name, json.dumps(cfg))
    )
    conn.commit()
    conn.close()
    flash(f"部署配置「{display_name}」已添加", "success")
    return redirect(url_for("deployers_page"))


@app.route("/deployers/delete/<int:cid>")
@login_required
def deployer_delete(cid):
    """删除部署配置"""
    conn = get_db()
    conn.execute("DELETE FROM deployer_configs WHERE id=? AND user_id=?",
                 (cid, current_user.id))
    conn.commit()
    conn.close()
    flash("部署配置已删除", "success")
    return redirect(url_for("deployers_page"))


@app.route("/deployers/deploy/<int:cid>")
@login_required
def deployer_run(cid):
    """执行部署"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM deployer_configs WHERE id=? AND user_id=?",
        (cid, current_user.id)
    ).fetchone()
    if not row:
        conn.close()
        flash("部署配置不存在", "error")
        return redirect(url_for("deployers_page"))

    cfg = json.loads(row["config_json"]) if row["config_json"] else {}
    try:
        deployer = get_deployer(row["deployer_name"], cfg)
        result = deployer.deploy()
        conn.execute(
            "INSERT INTO deploy_log (config_id, deployer_name, success, url, error, message) VALUES (?, ?, ?, ?, ?, ?)",
            (cid, row["deployer_name"],
             1 if result.get("success") else 0,
             result.get("url", ""),
             result.get("error", ""),
             result.get("message", ""))
        )
        conn.commit()

        if result.get("success"):
            msg = result.get("message", "部署成功")
            flash(f"✅ {msg}", "success")
            # 更新所有 pending 的发布记录为 deployed
            conn.execute(
                "UPDATE publish_log SET deploy_status='deployed', updated_at=datetime('now') "
                "WHERE deploy_status='pending' OR deploy_status IS NULL"
            )
            conn.commit()
            conn.close()
            # GitHub Pages 部署延迟提示
            if row["deployer_name"] == "github_pages":
                flash("⏳ GitHub Pages 需要 1-2 分钟刷新，请稍后访问站点确认", "info")
        else:
            flash(f"❌ 部署失败: {result.get('error', '未知错误')}", "error")
            conn.close()
    except Exception as e:
        conn.execute(
            "INSERT INTO deploy_log (config_id, deployer_name, success, error) VALUES (?, ?, 0, ?)",
            (cid, row["deployer_name"], str(e))
        )
        conn.commit()
        conn.close()
        flash(f"❌ 部署异常: {e}", "error")

    return redirect(url_for("deployers_page"))


@app.route("/deployers/test/<int:cid>")
@login_required
def deployer_test(cid):
    """测试部署配置连接"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM deployer_configs WHERE id=? AND user_id=?",
        (cid, current_user.id)
    ).fetchone()
    conn.close()
    if not row:
        flash("部署配置不存在", "error")
        return redirect(url_for("deployers_page"))

    cfg = json.loads(row["config_json"]) if row["config_json"] else {}
    try:
        deployer = get_deployer(row["deployer_name"], cfg)
        result = deployer.test_connection()
        if result.get("success"):
            flash(f"✅ 连接正常: {result.get('status', '')}", "success")
        else:
            flash(f"❌ 连接失败: {result.get('error', '')}", "error")
    except Exception as e:
        flash(f"❌ 测试异常: {e}", "error")

    return redirect(url_for("deployers_page"))

# ─── 评论监控 ──────────────────────────────────
from flashsloth.plugins.reply_monitor import ReplyMonitor, DiscuzReplyExtractor, AutoReplyEngine

_reply_monitor = ReplyMonitor()

@login_required
@app.route("/comment-monitor")
def comment_monitor():
    """评论监控主页 — 所有帖子 + 回复统一管理"""
    conn = get_db()
    # 所有论坛账号
    discuz_accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE platform='discuz' AND is_active=1 "
        "AND config_json LIKE '%site_url%' ORDER BY account_name"
    ).fetchall()

    # 监控配置
    configs = {}
    for cfg in conn.execute("SELECT * FROM comment_monitor_config").fetchall():
        configs[cfg["account_id"]] = dict(cfg)

    # 统计
    data = _reply_monitor.get_stats()
    all_posts = data["all_posts"]
    stats = data["stats"]

    # 合并：为每个帖子附加回复统计
    stat_map = {}
    for s in stats:
        key = f"{s['article_id']}_{s['thread_tid']}"
        stat_map[key] = s

    forum_posts = []
    for p in all_posts:
        key = f"{p['article_id']}_{p['tid']}"
        s = stat_map.get(key, {})
        forum_posts.append({
            **p,
            "reply_count": s.get("reply_count", 0) if s else 0,
            "unread_count": s.get("unread_count", 0) if s else 0,
            "last_reply_at": s.get("last_reply_at", "") if s else "",
            "forum_name": s.get("forum_name", "") if s else "",
        })

    # 按平台分组
    grouped = {}
    for p in forum_posts:
        site = p.get("site_url", "").replace("https://", "").split(".")[0]
        key = site or p["platform"]
        grouped.setdefault(key, []).append(p)

    # 总未读
    total_unread = conn.execute(
        "SELECT COUNT(*) FROM comment_replies WHERE is_read=0"
    ).fetchone()[0]

    conn.close()

    return render_template("comment_monitor.html",
                         grouped=grouped,
                         discuz_accounts=[dict(a) for a in discuz_accounts],
                         configs=configs,
                         total_unread=total_unread,
                         now=datetime.now())


@login_required
@app.route("/api/comment-monitor/check/<int:account_id>", methods=["POST"])
def api_cm_check(account_id):
    """手动触发回复检查"""
    result = _reply_monitor.check_account_replies(account_id)
    return jsonify(result)


@login_required
@app.route("/api/comment-monitor/check-all", methods=["POST"])
def api_cm_check_all():
    """检查所有论坛账号"""
    results = _reply_monitor.check_all_accounts()
    total_new = sum(r.get("new_replies", 0) for r in results)
    return jsonify({
        "success": True,
        "total_new": total_new,
        "accounts": results,
    })


@login_required
@app.route("/api/comment-monitor/config/<int:account_id>", methods=["GET", "POST"])
def api_cm_config(account_id):
    """获取/更新评论监控配置"""
    conn = get_db()

    if request.method == "GET":
        cfg = conn.execute(
            "SELECT * FROM comment_monitor_config WHERE account_id=?",
            (account_id,)
        ).fetchone()
        conn.close()
        if cfg:
            return jsonify({"success": True, "config": dict(cfg)})
        # 默认配置
        return jsonify({
            "success": True,
            "config": {
                "account_id": account_id,
                "enabled": 1,
                "slot_morning": "12:00-12:30",
                "slot_afternoon": "15:00-15:30",
                "slot_evening": "20:00-20:30",
                "auto_reply": 0,
                "reply_style": "friendly",
                "reply_tone": "热心帮助",
                "max_replies_per_day": 3,
                "notify_replies": 1,
            }
        })

    # POST: 保存配置
    data = request.json
    conn.execute(
        """INSERT INTO comment_monitor_config
           (account_id, enabled, slot_morning, slot_afternoon, slot_evening,
            auto_reply, reply_style, reply_tone, max_replies_per_day, notify_replies)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(account_id) DO UPDATE SET
           enabled=excluded.enabled, slot_morning=excluded.slot_morning,
           slot_afternoon=excluded.slot_afternoon, slot_evening=excluded.slot_evening,
           auto_reply=excluded.auto_reply, reply_style=excluded.reply_style,
           reply_tone=excluded.reply_tone, max_replies_per_day=excluded.max_replies_per_day,
           notify_replies=excluded.notify_replies, updated_at=datetime('now')""",
        (account_id,
         data.get("enabled", 1),
         data.get("slot_morning", "12:00-12:30"),
         data.get("slot_afternoon", "15:00-15:30"),
         data.get("slot_evening", "20:00-20:30"),
         data.get("auto_reply", 0),
         data.get("reply_style", "friendly"),
         data.get("reply_tone", "热心帮助"),
         data.get("max_replies_per_day", 3),
         data.get("notify_replies", 1))
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "配置已保存"})


@login_required
@app.route("/api/comment-monitor/replies/<int:article_id>")
def api_cm_replies(article_id):
    """获取某篇文章在某个论坛的全部回复"""
    platform = request.args.get("platform", "")
    thread_tid = request.args.get("tid", "")
    conn = get_db()
    if thread_tid:
        rows = conn.execute(
            "SELECT * FROM comment_replies WHERE article_id=? AND thread_tid=? "
            "ORDER BY created_at DESC",
            (article_id, thread_tid)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM comment_replies WHERE article_id=? "
            "ORDER BY created_at DESC",
            (article_id,)
        ).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "replies": [dict(r) for r in rows],
        "total": len(rows),
    })


@login_required
@app.route("/api/comment-monitor/mark-read", methods=["POST"])
def api_cm_mark_read():
    """标记回复为已读"""
    reply_ids = request.json.get("ids", [])
    all_replies = request.json.get("all", False)
    conn = get_db()
    if all_replies:
        conn.execute("UPDATE comment_replies SET is_read=1")
    elif reply_ids:
        placeholders = ",".join("?" for _ in reply_ids)
        conn.execute(
            f"UPDATE comment_replies SET is_read=1 WHERE id IN ({placeholders})",
            reply_ids
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@login_required
@app.route("/api/comment-monitor/auto-reply/<int:reply_id>", methods=["POST"])
def api_cm_auto_reply(reply_id):
    """AI 自动回帖"""
    conn = get_db()
    reply = conn.execute("SELECT * FROM comment_replies WHERE id=?", (reply_id,)).fetchone()
    if not reply:
        conn.close()
        return jsonify({"success": False, "error": "回复不存在"})

    reply = dict(reply)

    # 获取账号配置
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=?", (reply["account_id"],)
    ).fetchone()
    if not acct:
        conn.close()
        return jsonify({"success": False, "error": "账号不存在"})

    acct_dict = dict(acct)
    cfg = json.loads(acct_dict.get("config_json", "{}"))

    # 获取监控配置
    mon_cfg = conn.execute(
        "SELECT * FROM comment_monitor_config WHERE account_id=?",
        (reply["account_id"],)
    ).fetchone()
    style = "friendly"
    tone = "热心帮助"
    if mon_cfg:
        style = mon_cfg["reply_style"] or "friendly"
        tone = mon_cfg["reply_tone"] or "热心帮助"

    conn.close()

    # 获取帖子原文（用浏览器的简短抓取）
    try:
        extractor = DiscuzReplyExtractor(
            site_url=cfg.get("site_url", ""),
            cookies=cfg.get("cookie", ""),
            username=cfg.get("username", acct_dict["account_name"]),
        )
        detail = extractor.get_replies_for_thread(reply["thread_tid"])
        thread_content = ""
        if detail["replies"]:
            thread_content = detail["replies"][0]["content"] if detail["replies"] else ""
    except:
        thread_content = ""

    # AI 生成回复
    engine = AutoReplyEngine()
    reply_text = engine.generate_reply(
        thread_title=reply["thread_title"] or "",
        thread_content=thread_content or "",
        reply_content=reply["reply_content"] or "",
        reply_author=reply["reply_author"] or "",
        style=style,
        tone=tone,
    )

    # 如果开启了自动回复，自动提交并记录
    if mon_cfg and mon_cfg.get("auto_reply"):
        from flashsloth.plugins.browser_session import HumanSession
        try:
            browser = HumanSession(base_url=cfg.get("site_url", ""), min_delay=1.0, max_delay=3.0)
            if cfg.get("cookie"):
                browser.set_cookies(cfg["cookie"])
            browser.get(f"/forum.php?mod=viewthread&tid={reply['thread_tid']}")
            import time, random
            time.sleep(random.uniform(2, 4))
            formhash = browser.get_formhash(f"/forum.php?mod=viewthread&tid={reply['thread_tid']}")
            if formhash:
                time.sleep(random.uniform(0.5, 1.5))
                post_data = {
                    "formhash": formhash,
                    "message": reply_text,
                    "replysubmit": "yes",
                    "posttime": str(int(time.time()) - random.randint(10, 60)),
                    "wysiwyg": "0",
                }
                resp = browser.post(
                    f"/forum.php?mod=post&action=reply&tid={reply['thread_tid']}"
                    f"&extra=&replysubmit=yes&infloat=yes&handlekey=fastpost",
                    data=post_data,
                )
                auto_success = "回复发布成功" in resp.text or "发表于" in resp.text
                auto_error = "" if auto_success else "自动提交失败"
                conn = get_db()
                conn.execute(
                    "INSERT INTO auto_reply_log (reply_id, article_id, account_id, platform, "
                    "thread_tid, reply_content, ai_model, success, error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (reply_id, reply["article_id"], reply["account_id"],
                     reply["platform"], reply["thread_tid"],
                     reply_text[:500], style,
                     1 if auto_success else 0, auto_error)
                )
                conn.commit()
                conn.close()
                if auto_success:
                    conn = get_db()
                    conn.execute(
                        "UPDATE comment_replies SET is_auto_replied=1 WHERE id=?",
                        (reply_id,)
                    )
                    conn.commit()
                    conn.close()
                    return jsonify({
                        "success": True,
                        "reply_text": reply_text,
                        "tid": reply["thread_tid"],
                        "site_url": cfg.get("site_url", ""),
                        "account_id": reply["account_id"],
                        "reply_id": reply_id,
                        "auto_submitted": True,
                        "message": "🤖 已自动回复",
                    })
        except Exception as e:
            pass  # 自动回复失败不阻塞

    return jsonify({
        "success": True,
        "reply_text": reply_text,
        "tid": reply["thread_tid"],
        "site_url": cfg.get("site_url", ""),
        "account_id": reply["account_id"],
        "reply_id": reply_id,
        "auto_submitted": False,
    })


@login_required
@app.route("/api/comment-monitor/reply-submit", methods=["POST"])
def api_cm_reply_submit():
    """将生成的回复提交到论坛（用浏览器模拟发帖）"""
    tid = request.json.get("tid", "")
    reply_text = request.json.get("reply_text", "")
    account_id = request.json.get("account_id", 0)

    if not tid or not reply_text or not account_id:
        return jsonify({"success": False, "error": "缺少参数"})

    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND is_active=1",
        (account_id,)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    acct_dict = dict(acct)
    cfg = json.loads(acct_dict.get("config_json", "{}"))
    site_url = cfg.get("site_url", "")

    try:
        browser = HumanSession(base_url=site_url, min_delay=1.0, max_delay=3.0)
        if cfg.get("cookie"):
            browser.set_cookies(cfg["cookie"])

        # 模拟人的操作：先看帖子，再回复
        browser.get(f"/forum.php?mod=viewthread&tid={tid}")
        time.sleep(random.uniform(2, 4))

        # 获取 formhash
        formhash = browser.get_formhash(f"/forum.php?mod=viewthread&tid={tid}")
        if not formhash:
            return jsonify({"success": False, "error": "无法获取 formhash，Cookie 可能过期"})

        # 模拟打字延迟，分段写入
        time.sleep(random.uniform(0.5, 1.5))

        # 提交回复
        post_data = {
            "formhash": formhash,
            "message": reply_text,
            "replysubmit": "yes",
            "posttime": str(int(time.time()) - random.randint(10, 60)),
            "wysiwyg": "0",
        }

        resp = browser.post(
            f"/forum.php?mod=post&action=reply&tid={tid}&extra=&replysubmit=yes&infloat=yes&handlekey=fastpost",
            data=post_data,
        )

        # 检查是否成功
        if "回复发布成功" in resp.text or "发表于" in resp.text or tid in resp.text:
            return jsonify({
                "success": True,
                "message": "回复成功 ✅",
                "url": f"{site_url}/forum.php?mod=viewthread&tid={tid}",
            })
        if "您的请求来路不正确" in resp.text:
            return jsonify({"success": False, "error": "表单验证失败（来路不正确）"})
        if "抱歉" in resp.text and "限制" in resp.text:
            return jsonify({"success": False, "error": "发帖受限（尚在禁言期或需要审核）"})

        # 提取错误信息
        err = ""
        for pat in [
            r'<div[^>]*class="alert_error"[^>]*>([\\s\\S]*?)</div>',
            r'<p[^>]*class="alert_info"[^>]*>(.*?)</p>',
        ]:
            m = re.search(pat, resp.text, re.DOTALL)
            if m:
                err = re.sub(r"<[^>]+>", "", m.group(1)).strip()[:100]
                break

        return jsonify({
            "success": False,
            "error": err or "回复失败，可能被论坛拦截",
            "need_human": True,
        })

    except Exception as e:
        return jsonify({"success": False, "error": f"提交异常: {e}"})


# ─── AI 逛论坛 ──────────────────────────────────
from flashsloth.plugins.forum_reader import DiscuzForumReader, InterestFilter

_interest_filter = InterestFilter()

@app.route("/forum-reader")
@login_required
def forum_reader():
    """AI逛论坛 — 推荐 + 浏览 + 回复汇总"""
    conn = get_db()
    # 获取最近推荐
    recs = conn.execute(
        "SELECT * FROM forum_recommendations WHERE user_id=? "
        "ORDER BY score DESC, created_at DESC LIMIT 100",
        (current_user.id,)
    ).fetchall()
    # 获取用户已配置的 Discuz! 类平台账号
    discuz_accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? AND platform='discuz' AND is_active=1",
        (current_user.id,)
    ).fetchall()
    # 统计未读
    unread = conn.execute(
        "SELECT COUNT(*) FROM forum_recommendations WHERE user_id=? AND is_read=0",
        (current_user.id,)
    ).fetchone()[0]
    conn.close()
    return render_template("forum_reader.html",
                         recommendations=[dict(r) for r in recs],
                         discuz_accounts=[dict(a) for a in discuz_accounts],
                         unread=unread,
                         publishers=list_publishers())


@app.route("/api/forum-reader/browse", methods=["POST"])
@login_required
def api_forum_browse():
    """浏览指定论坛并抓取新帖"""
    account_id = request.json.get("account_id")
    hours = request.json.get("hours", 24)
    if not account_id:
        return jsonify({"success": False, "error": "请选择论坛账号"})
    account_id = int(account_id)
    hours = int(hours)

    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (account_id, current_user.id)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    site_url = cfg.get("site_url", "")
    cookies = cfg.get("cookie", "")
    username = cfg.get("username", acct["account_name"])

    if not site_url:
        return jsonify({"success": False, "error": "论坛地址未配置"})

    reader = DiscuzForumReader(site_url, cookies=cookies, username=username)

    # 获取板块列表
    forums = reader.get_forum_list()
    if not forums:
        return jsonify({"success": False, "error": "无法获取板块列表，请检查 Cookie 是否有效"})

    # 遍历板块抓取新帖
    all_threads = []
    for f in forums[:5]:  # 限制前5个板块
        threads = reader.get_new_threads(f["fid"], hours=hours, max_pages=2)
        for t in threads:
            t["forum_name"] = f["name"]
        all_threads.extend(threads)

    # AI 筛选
    filtered = _interest_filter.filter_threads(all_threads)

    # 获取详细内容（对高分帖子）
    top_threads = []
    for t in filtered[:20]:
        detail = reader.get_thread_detail(t["tid"])
        t["content"] = detail["content"] if detail else ""
        t["author"] = detail["author"] if detail else ""
        top_threads.append(t)

    # 存入数据库
    conn = get_db()
    new_count = 0
    for t in top_threads:
        # 去重
        existing = conn.execute(
            "SELECT id FROM forum_recommendations WHERE user_id=? AND platform=? AND tid=? AND url=?",
            (current_user.id, "discuz", t["tid"], t["url"])
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO forum_recommendations (user_id, platform, forum_name, title, url, tid, fid, "
            "author, content, tags, score, summary, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (current_user.id, "discuz", t.get("forum_name", ""), t["title"], t["url"],
             t["tid"], t.get("fid", ""), t.get("author", ""),
             t.get("content", "")[:500], json.dumps(t.get("ai_tags", [])),
             t["ai_score"], t.get("ai_summary", ""), "keyword")
        )
        new_count += 1
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "total": len(all_threads),
        "filtered": len(filtered),
        "new_saved": new_count,
        "forums": [f["name"] for f in forums],
        "samples": top_threads[:5],
    })


@app.route("/api/forum-reader/replies", methods=["POST"])
@login_required
def api_forum_replies():
    """检查我的帖子的回复"""
    account_id = request.json.get("account_id")
    if not account_id:
        return jsonify({"success": False, "error": "请选择论坛账号"})
    account_id = int(account_id)

    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (account_id, current_user.id)
    ).fetchone()

    # 查找当前用户在该论坛已发布的帖子
    my_threads = conn.execute(
        "SELECT pl.url, pl.article_id FROM publish_log pl "
        "LEFT JOIN articles a ON pl.article_id=a.id "
        "WHERE pl.account_id=? AND pl.success=1 AND a.user_id=?",
        (account_id, current_user.id)
    ).fetchall()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    site_url = cfg.get("site_url", "")
    cookies = cfg.get("cookie", "")
    username = cfg.get("username", acct["account_name"])

    reader = DiscuzForumReader(site_url, cookies=cookies, username=username)

    # 从发布记录中提取 tid
    tids = []
    for t in my_threads:
        m = re.search(r"tid=(\d+)", t["url"] or "")
        if m:
            tids.append(m.group(1))

    replies = reader.get_replies_to_my_threads(tids)

    # 存入数据库（标记为我的帖子回复）
    conn = get_db()
    new_count = 0
    for r in replies:
        existing = conn.execute(
            "SELECT id FROM forum_recommendations WHERE user_id=? AND platform='discuz' "
            "AND url=? AND source='reply'",
            (current_user.id, r["url"])
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO forum_recommendations (user_id, platform, title, url, "
            "reply_author, reply_content, source, is_my_thread) VALUES (?, ?, ?, ?, ?, ?, 'reply', 1)",
            (current_user.id, f"discuz ({r.get('author','')})", f"回复: {r.get('content','')[:80]}",
             r["url"], r.get("author", ""), r.get("content", "")[:200])
        )
        new_count += 1
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "new_replies": new_count,
        "total_replies": len(replies),
    })


@app.route("/api/forum-reader/mark-read/<int:rid>")
@login_required
def api_forum_mark_read(rid):
    """标记推荐为已读"""
    conn = get_db()
    conn.execute(
        "UPDATE forum_recommendations SET is_read=1 WHERE id=? AND user_id=?",
        (rid, current_user.id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/forum-reader/get-forums/<int:account_id>")
@login_required
def api_get_forums(account_id):
    """获取 Discuz 论坛板块列表"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (account_id, current_user.id)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    site_url = cfg.get("site_url", "")
    cookies = cfg.get("cookie", "")
    username = cfg.get("username", acct["account_name"])

    if not site_url:
        return jsonify({"success": False, "error": "论坛地址未配置"})

    reader = DiscuzForumReader(site_url, cookies=cookies, username=username)
    forums = reader.get_forum_list()

    return jsonify({"success": True, "forums": forums})


@app.route("/api/forum-reader/clear-old")
@login_required
def api_forum_clear_old():
    """清理7天前的已读推荐"""
    conn = get_db()
    deleted = conn.execute(
        "DELETE FROM forum_recommendations WHERE user_id=? AND is_read=1 "
        "AND created_at < datetime('now', '-7 days')",
        (current_user.id,)
    ).rowcount
    conn.commit()
    conn.close()
    return jsonify({"success": True, "deleted": deleted})


# ─── 签到管理 ──────────────────────────────────
@app.route("/signin")
@login_required
def signin_page():
    """签到页面 — 查看状态 + 手动签到"""
    conn = get_db()

    # 所有活跃账号
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE is_active=1 ORDER BY platform, account_name"
    ).fetchall()

    # 签到调度配置（每个账号一条）
    schedules = {}
    for s in conn.execute("SELECT * FROM signin_schedules").fetchall():
        schedules[s["account_id"]] = dict(s)

    # 最近签到记录
    logs = conn.execute(
        "SELECT * FROM signin_log ORDER BY created_at DESC LIMIT 30"
    ).fetchall()

    # 统计
    today = datetime.now().strftime("%Y-%m-%d")
    today_count = conn.execute(
        "SELECT COUNT(*) FROM signin_log WHERE date(created_at)=? AND success=1",
        (today,)
    ).fetchone()[0]

    conn.close()

    return render_template("signin.html",
                         accounts=[dict(a) for a in accounts],
                         logs=[dict(l) for l in logs],
                         today_count=today_count,
                         schedules=schedules)


@app.route("/api/signin/run", methods=["POST"])
@login_required
def api_signin_run():
    """手动执行签到"""
    account_id = request.form.get("account_id", type=int)

    # 动态加载 orchestrator
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from plugins.forum_signin import main as run_signin_main

    # 捕获输出
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        run_signin_main()
    output = buf.getvalue()

    return jsonify({"success": True, "output": output})


@app.route("/api/signin/schedules", methods=["POST"])
@login_required
def api_signin_schedules():
    """批量保存签到时间调度"""
    data = request.get_json(force=True)
    schedules = data.get("schedules", [])  # [{account_id, time_start, time_end, enabled}]
    conn = get_db()
    count = 0
    for s in schedules:
        aid = s.get("account_id")
        if not aid:
            continue
        ts = s.get("time_start", "08:00")
        te = s.get("time_end", "08:00")
        en = s.get("enabled", 1)
        conn.execute(
            """INSERT INTO signin_schedules (account_id, time_start, time_end, enabled)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(account_id) DO UPDATE SET
               time_start=excluded.time_start, time_end=excluded.time_end,
               enabled=excluded.enabled, updated_at=datetime('now')""",
            (aid, ts, te, en)
        )
        count += 1
    conn.commit()
    conn.close()
    return jsonify({"success": True, "saved": count})


# ─── 数据导出导入 ──────────────────────────────────
@app.route("/api/export")
@login_required
def api_export():
    """导出全部数据为 zip 包"""
    import tempfile
    base = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base, "flashsloth.db")
    uploads_dir = os.path.join(base, "static", "uploads")
    config_path = os.path.join(base, "flashsloth.yml")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(db_path):
            zf.write(db_path, "flashsloth.db")
        if os.path.exists(uploads_dir):
            for root, dirs, files in os.walk(uploads_dir):
                for fn in files:
                    fpath = os.path.join(root, fn)
                    arcname = os.path.relpath(fpath, base)
                    zf.write(fpath, arcname)
        if os.path.exists(config_path):
            zf.write(config_path, "flashsloth.yml")
        info = {
            "exported_at": datetime.now().isoformat(),
            "version": "1.0",
        }
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            info["tables"] = [r[0] for r in rows]
            conn.close()
        zf.writestr("manifest.json", json.dumps(info, ensure_ascii=False, indent=2))

    buf.seek(0)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "application/zip"
    resp.headers["Content-Disposition"] = f'attachment; filename="flashsloth_backup_{ts}.zip"'
    return resp


@app.route("/api/import", methods=["POST"])
@login_required
def api_import():
    """导入 zip 备份包恢复数据"""
    import tempfile
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未选择文件"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".zip"):
        return jsonify({"success": False, "error": "仅支持 .zip 文件"}), 400

    base = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base, "flashsloth.db")
    uploads_dir = os.path.join(base, "static", "uploads")

    tmpdir = tempfile.mkdtemp(prefix="fs_import_")
    try:
        f.save(os.path.join(tmpdir, "import.zip"))
        with zipfile.ZipFile(os.path.join(tmpdir, "import.zip"), "r") as zf:
            zf.extractall(tmpdir)
        manifest_path = os.path.join(tmpdir, "manifest.json")
        if not os.path.exists(manifest_path):
            return jsonify({"success": False, "error": "无效备份包: 缺少 manifest.json"}), 400
        with open(manifest_path) as mf:
            manifest = json.load(mf)

        # 自动备份当前数据
        bak_dir = os.path.join(base, "static", "backups")
        os.makedirs(bak_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak_path = os.path.join(bak_dir, f"pre_import_backup_{ts}")
        os.makedirs(bak_path)
        if os.path.exists(db_path):
            shutil.copy2(db_path, os.path.join(bak_path, "flashsloth.db"))
        if os.path.exists(uploads_dir):
            shutil.copytree(uploads_dir, os.path.join(bak_path, "uploads"),
                            dirs_exist_ok=True)

        # 恢复
        import_db = os.path.join(tmpdir, "flashsloth.db")
        if os.path.exists(import_db):
            shutil.copy2(import_db, db_path)
        import_uploads = os.path.join(tmpdir, "static", "uploads")
        if os.path.exists(import_uploads):
            shutil.copytree(import_uploads, uploads_dir, dirs_exist_ok=True)
        import_config = os.path.join(tmpdir, "flashsloth.yml")
        if os.path.exists(import_config):
            shutil.copy2(import_config, os.path.join(base, "flashsloth.yml"))

        return jsonify({
            "success": True,
            "message": f"导入成功！原数据已备份到 static/backups/pre_import_backup_{ts}/",
            "tables": manifest.get("tables", []),
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"导入失败: {e}"}), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ─── 启动 ───────────────────────────────────────
if __name__ == "__main__":
    init_db()
    host = os.environ.get("FLASHSLOTH_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASHSLOTH_PORT", "5000"))
    print("=" * 54)
    print("  🦥 FlashSloth — 树懒的速度，闪电的发布")
    print(f"  🌐 http://{host}:{port}")
    if _BOOT_CREDENTIALS:
        u, p = _BOOT_CREDENTIALS
        print(f"  👤 首次启动，自动生成了管理员账号：")
        print(f"     用户名: {u}")
        print(f"     密码:   {p}")
        print(f"  ⚠️  请尽快登录后台修改密码！")
    else:
        print("  🔑 已有账号，请使用注册的账号登录")
    print("=" * 54)
    app.run(host=host, port=port, debug=False)
