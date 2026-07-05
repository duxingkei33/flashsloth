"""FlashSloth 数据库核心 — DB初始化、连接、迁移

从 admin.py 提取，保持100%兼容。
"""
import os, json, random, string, hashlib, hmac, time, base64, re, threading
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")

# 首次启动生成的随机 admin 凭证
_BOOT_CREDENTIALS = None


def get_db():
    """获取数据库连接（每次请求新建，避免多线程竞争）"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构 + 迁移 + 首次自动创建管理员"""
    global _BOOT_CREDENTIALS
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
        CREATE TABLE IF NOT EXISTS ai_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            alias TEXT NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            api_base TEXT DEFAULT '',
            api_format TEXT DEFAULT 'openai',
            models TEXT DEFAULT '[]',
            status TEXT DEFAULT 'untested',
            created_at TEXT DEFAULT (datetime('now')),
            balance TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            UNIQUE(user_id, provider, alias)
        );
    """)
    conn.commit()

    # ─── 迁移：添加 ai_configs 新字段 ───
    from flashsloth.core.provider_registry import get_registry
    try:
        conn.execute("ALTER TABLE ai_configs ADD COLUMN balance TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE ai_configs ADD COLUMN enabled INTEGER DEFAULT 1")
    except Exception:
        pass
    # 迁移：platform_accounts 添加状态和保持在线字段
    for col in ["status", "keep_alive", "last_status_check"]:
        try:
            conn.execute(f"ALTER TABLE platform_accounts ADD COLUMN {col} TEXT DEFAULT ''")
        except Exception:
            pass
    try:
        conn.execute("ALTER TABLE platform_accounts ADD COLUMN keep_alive INTEGER DEFAULT 0")
    except Exception:
        pass
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
        _BOOT_CREDENTIALS = (admin_user, admin_pass)
        # 同时写入文件，避免终端输出被缓冲吞掉
        cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".boot_credentials")
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
    return f"{a} {op} {b} = ?", str(ans)


def send_sms_code(phone: str, code: str) -> bool:
    """发送短信验证码（预留接口，目前仅打日志）"""
    print(f"[SMS] 验证码 {code} → {phone}")
    return True


def generate_token(uid: int, action: str = "auth") -> str:
    """生成一次性 token（用于找回密码等）"""
    raw = f"{uid}:{action}:{time.time()}:{os.urandom(8).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_boot_credentials():
    """获取首次启动生成的临时凭证"""
    return _BOOT_CREDENTIALS
