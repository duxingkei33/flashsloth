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


# ─── 论坛探索种子数据（从JSON文件加载）──────────
def _seed_forum_exploration(conn):
    """从 platform_reports/*.json + config/platform_*.json 加载探索数据到 forum_exploration 表"""
    import json
    root = os.path.dirname(os.path.dirname(__file__))
    reports_dir = os.path.join(root, "platform_reports")
    config_dir = os.path.join(root, "config")
    
    # 检查是否已有数据——如果已有则不覆盖，除非 force=True
    global_count = conn.execute("SELECT COUNT(*) FROM forum_exploration").fetchone()[0]
    count = 0
    if global_count <= 20:
        # ─── 从 platform_reports/ 加载论坛板块数据 ───
        platform_map = {
            "amobbs_com_forums": ("discuz_amobbs", "amobbs.com", "阿莫电子论坛"),
            "mydigit_cn_forums": ("discuz_mydigit", "mydigit.cn", "数码之家"),
        }

        count = 0
        for prefix, (platform_name, domain, display) in platform_map.items():
            json_path = os.path.join(reports_dir, f"{prefix}.json")
            if not os.path.exists(json_path):
                print(f"  [种子] 跳过 {prefix}：文件不存在")
                continue

            with open(json_path) as f:
                data = json.load(f)

            forums = data.get("forums", {})
            inserted = 0
            for fid, info in forums.items():
                can_post = info.get("can_post", False)
                if not can_post:
                    continue
                name = info.get("name", f"fid={fid}")
                keywords = json.dumps([name], ensure_ascii=False)
                extra = json.dumps({
                    "href": info.get("href", ""),
                    "postable": True,
                }, ensure_ascii=False)

                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO forum_exploration 
                           (platform, platform_domain, section_id, section_name, can_post, keywords, extra_info)
                           VALUES (?, ?, ?, ?, 1, ?, ?)""",
                        (platform_name, domain, fid, name, keywords, extra)
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  [种子] 插入失败 {domain}/{fid}: {e}")

            conn.commit()
            count += inserted
            print(f"  [种子] {display} ({domain}): 已导入 {inserted} 个版块")
        print(f"  [种子] 论坛板块导入完成，共 {count} 条")
    else:
        print(f"  [种子] 已有 {global_count} 条探索数据，跳过 forum_sections 导入（预设配置仍会加载）")

    # ─── 从 config/platform_*.json 加载增强数据（预设配置）───
    preset_map = {
        "platform_amobbs": ("discuz_amobbs", "amobbs.com"),
        "platform_mydigit": ("discuz_mydigit", "mydigit.cn"),
        "platform_csdn": ("csdn", "csdn.net"),
        "platform_zhihu": ("zhihu", "zhihu.com"),
    }
    for preset_name, (plat, dom) in preset_map.items():
        preset_path = os.path.join(config_dir, f"{preset_name}.json")
        if not os.path.exists(preset_path):
            continue
        try:
            with open(preset_path) as f:
                preset = json.load(f)
        except Exception as e:
            print(f"  [种子] 跳过 preset {preset_name}: {e}")
            continue
        
        # 从预设配置更新关键词（修复：sections可能是list，无需tags_of_interest存在）
        raw_sections = preset.get("sections", [])
        if isinstance(raw_sections, dict):
            raw_sections = list(raw_sections.values())
        if raw_sections and isinstance(raw_sections, list):
            updated = 0
            for section in raw_sections:
                sid = str(section.get("id", section.get("section_id", "")))
                kw = section.get("keywords", [])
                if isinstance(kw, str):
                    kw = [kw]
                if not kw:
                    kw = [section.get("name", sid)]
                extra_tags = json.dumps(kw, ensure_ascii=False)
                r = conn.execute(
                    "UPDATE forum_exploration SET keywords=? WHERE platform_domain=? AND section_id=?",
                    (extra_tags, dom, sid)
                )
                if r.rowcount > 0:
                    updated += 1
            if updated:
                conn.commit()
                print(f"  [种子] {preset_name}: 更新了 {updated} 个版块的关键词")
        
        # 存储平台能力到预设
        caps = preset.get("capabilities", {})
        if caps:
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO platform_config (platform, platform_domain, config_json) VALUES (?, ?, ?)",
                    (plat, dom, json.dumps(caps, ensure_ascii=False))
                )
                conn.commit()
                print(f"  [种子] {preset_name}: 存储了平台能力配置")
            except Exception as e:
                print(f"  [种子] {preset_name} 存储配置失败: {e}")
    
    # OSHWHub项目类型
    oshwhub_types = [
        ("oshwhub", "oshwhub.com", "project", "工程", "创建开源硬件工程"),
        ("oshwhub", "oshwhub.com", "article", "文章", "撰写技术文章/教程"),
    ]
    for pn, dom, sid, sname, desc in oshwhub_types:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO forum_exploration 
                   (platform, platform_domain, section_id, section_name, can_post, keywords, extra_info)
                   VALUES (?, ?, ?, ?, 1, ?, ?)""",
                (pn, dom, sid, sname, json.dumps([sname, desc], ensure_ascii=False),
                 json.dumps({"endpoint": f"/{sid}/create", "desc": desc}, ensure_ascii=False))
            )
        except Exception:
            pass
    conn.commit()
    
    print(f"  [种子] 论坛探索数据: 共导入/更新 {count} 条板块记录")


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
            status TEXT DEFAULT 'draft',
            message TEXT DEFAULT '',
            deploy_status TEXT DEFAULT '',
            retracted_at TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
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
        CREATE TABLE IF NOT EXISTS forum_exploration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            platform_domain TEXT NOT NULL,
            section_id TEXT NOT NULL,
            section_name TEXT NOT NULL,
            can_post INTEGER DEFAULT 1,
            keywords TEXT DEFAULT '[]',
            extra_info TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(platform_domain, section_id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT DEFAULT '',
            level TEXT DEFAULT 'info',
            source TEXT DEFAULT 'system',
            link TEXT DEFAULT '',
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    # 迁移：添加 forum_exploration 兼容
    try:
        conn.execute("SELECT COUNT(*) FROM forum_exploration")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS forum_exploration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                platform_domain TEXT NOT NULL,
                section_id TEXT NOT NULL,
                section_name TEXT NOT NULL,
                can_post INTEGER DEFAULT 1,
                keywords TEXT DEFAULT '[]',
                extra_info TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(platform_domain, section_id)
            );
        """)
        conn.commit()

    # ─── 种子数据（从JSON文件加载探索数据）───
    _seed_forum_exploration(conn)

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
    # 迁移：platform_accounts 添加 sort_order（探索页排序用，不写死）
    try:
        conn.execute("ALTER TABLE platform_accounts ADD COLUMN sort_order INTEGER DEFAULT 0")
    except Exception:
        pass
    conn.commit()

    # 迁移：notifications 表（旧数据库兼容）
    try:
        conn.execute("SELECT COUNT(*) FROM notifications")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT DEFAULT '',
                level TEXT DEFAULT 'info',
                source TEXT DEFAULT 'system',
                link TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

    # 迁移：platform_config 表（平台能力配置）
    try:
        conn.execute("SELECT COUNT(*) FROM platform_config")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS platform_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                platform_domain TEXT NOT NULL,
                config_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(platform, platform_domain)
            );
        """)
        conn.commit()

    # 迁移：forum_exploration 添加 tags_of_interest 列
    for col in ["tags_of_interest"]:
        try:
            conn.execute(f"ALTER TABLE forum_exploration ADD COLUMN {col} TEXT DEFAULT '[]'")
        except Exception:
            pass
    conn.commit()

    # 迁移：site_configs 表（站点全局部署配置 — 博客平台/评论系统/插件）
    try:
        conn.execute("SELECT COUNT(*) FROM site_configs")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS site_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                deployer_id INTEGER,
                platform TEXT DEFAULT 'github_pages',
                comment_system TEXT DEFAULT '',
                comment_config TEXT DEFAULT '{}',
                plugins_config TEXT DEFAULT '{}',
                extra_config TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

    # 迁移：gateway_channels 表（通知网关终端配置）
    try:
        conn.execute("SELECT COUNT(*) FROM gateway_channels")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS gateway_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                platform TEXT NOT NULL,
                config_json TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 1,
                user_id INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

    # 迁移：playwright_config 表（浏览器引擎配置）
    try:
        conn.execute("SELECT COUNT(*) FROM playwright_config")
    except Exception:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS playwright_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                config_json TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        # 插入默认配置
        default_cfg = json.dumps({
            "browser_type": "chromium",
            "headless": True,
            "viewport_width": 1280,
            "viewport_height": 800,
            "user_agent": "",
            "timeout": 30000,
            "navigation_timeout": 30000,
            "locale": "zh-CN",
            "proxy": "",
            "data_dir": "",
            "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            "auto_start": True,
            "auto_close_minutes": 10,
            "qr_login_timeout_minutes": 10,
        })
        conn.execute(
            "INSERT OR IGNORE INTO playwright_config (id, config_json) VALUES (1, ?)",
            (default_cfg,),
        )
        conn.commit()

    # ─── ai_call_log ───
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ai_call_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                capability TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                prompt_tokens INTEGER DEFAULT 0,
                response_tokens INTEGER DEFAULT 0,
                cost REAL DEFAULT 0.0,
                success INTEGER DEFAULT 1,
                error TEXT DEFAULT '',
                response_summary TEXT DEFAULT '',
                prompt_preview TEXT DEFAULT '',
                user_id INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
    except Exception:
        pass

    # 迁移：ai_call_log 添加 user_id 字段
    try:
        conn.execute("ALTER TABLE ai_call_log ADD COLUMN user_id INTEGER DEFAULT 1")
    except Exception:
        pass

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
