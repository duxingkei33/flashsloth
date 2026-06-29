"""
FlashSloth Admin — 商用级多平台内容发布后台
功能：注册/登录/验证码/改密 / Provider选择 / Publisher多账号 / 一键发布
"""
import os, sys, json, random, string, hashlib, hmac, time, base64, re
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

app = Flask(__name__)
app.secret_key = os.environ.get("FLASHSLOTH_SECRET") or os.urandom(64).hex()
app.config["DEBUG"] = False

# 首次启动生成的随机 admin 凭证（见 init_db）
_BOOT_CREDENTIALS = None

DB_PATH = os.path.join(os.path.dirname(__file__), "flashsloth.db")

# ─── 数据库 ─────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
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
        return []
    try:
        return json.loads(val)
    except:
        return []

@app.template_filter("dict_get")
def dict_get_filter(d, key, default=""):
    return d.get(key, default) if d else default

# ─── 路由 ───────────────────────────────────────
@app.route("/")
@login_required
def index():
    conn = get_db()
    posts = conn.execute(
        "SELECT * FROM articles WHERE user_id=? ORDER BY updated_at DESC LIMIT 20",
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
            "WHERE pl.article_id=? AND pl.success=1 "
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
        try:
            publisher = get_publisher(acct["platform"], cfg)
            result = publisher.publish(article)
            conn.execute(
                "INSERT INTO publish_log (article_id, account_id, platform, success, url, error, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (article_id, aid, acct["platform"],
                 1 if result["success"] else 0,
                 result.get("url", ""), result.get("error", ""),
                 result.get("message", "")),
            )
            results.append(result)
        except Exception as e:
            conn.execute(
                "INSERT INTO publish_log (article_id, account_id, platform, success, error) VALUES (?, ?, ?, 0, ?)",
                (article_id, aid, acct["platform"], str(e)),
            )
            results.append({"success": False, "error": str(e)})

    if any(r["success"] for r in results):
        conn.execute("UPDATE articles SET status='published', updated_at=datetime('now') WHERE id=?", (article_id,))

    conn.commit()
    conn.close()

    success_count = sum(1 for r in results if r["success"])
    flash(f"发布完成: {success_count}/{len(results)} 成功", "success")
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
            # 更新发布日志状态
            conn2 = get_db()
            conn2.execute(
                "UPDATE publish_log SET status=?, retracted_at=datetime('now') WHERE id=?",
                ("retracted", log_id),
            )
            conn2.commit()
            conn2.close()
            flash(f"✅ 撤回成功: {result.get('message', '')}", "success")
            # 如果是 GitHub Pages，提醒部署
            if acct["platform"] == "github_pages_blog":
                flash("⏳ 请执行「部署」操作将变更同步到 GitHub Pages", "info")
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
    articles = conn.execute(
        "SELECT a.*, "
        "(SELECT COUNT(*) FROM publish_log pl WHERE pl.article_id=a.id AND pl.success=1 AND (pl.status='published' OR pl.status IS NULL)) as pub_count, "
        "(SELECT COUNT(*) FROM publish_log pl WHERE pl.article_id=a.id AND pl.status='retracted') as ret_count "
        "FROM articles a WHERE a.user_id=? ORDER BY a.updated_at DESC",
        (current_user.id,)
    ).fetchall()

    conn.close()

    return render_template("publish_manage.html",
                         logs=[dict(l) for l in logs],
                         articles=[dict(a) for a in articles])

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
