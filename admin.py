"""
FlashSloth Admin — 商用级多平台内容发布后台
功能：注册/登录/验证码/改密 / Provider选择 / Publisher多账号 / 一键发布
"""
import os, sys, json, random, string, hashlib, hmac, time, base64
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
from flashsloth.core.config import load_config
# 导入插件触发注册
import flashsloth.plugins.publisher_wordpress  # noqa
import flashsloth.plugins.publisher_wechat     # noqa
import flashsloth.plugins.publisher_juejin     # noqa
import flashsloth.plugins.publisher_rss        # noqa
import flashsloth.plugins.publisher_zhihu      # noqa
import flashsloth.plugins.publisher_csdn       # noqa

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
        CREATE TABLE IF NOT EXISTS verify_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            code TEXT NOT NULL,
            action TEXT DEFAULT 'register',
            expires_at TEXT,
            used INTEGER DEFAULT 0
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
    pconfig = conn.execute(
        "SELECT * FROM provider_config WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (current_user.id,)
    ).fetchone()
    conn.close()

    # 所有可用 platform
    pub_list = list_publishers()

    # 按平台分组账号
    account_map = {}
    for a in accounts:
        account_map.setdefault(a["platform"], []).append(dict(a))

    return render_template("index.html",
                         posts=posts, logs=logs,
                         publishers=pub_list,
                         account_map=account_map,
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
                "INSERT INTO publish_log (article_id, account_id, platform, success, url, error) VALUES (?, ?, ?, ?, ?, ?)",
                (article_id, aid, acct["platform"],
                 1 if result["success"] else 0,
                 result.get("url", ""), result.get("error", "")),
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
    conn.close()

    if not post:
        flash("文章不存在", "error")
        return redirect(url_for("index"))

    return render_template("publish_select.html",
                         post=post, accounts=accounts)

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
