"""
论坛签到 Orchestrator — 由 Hermes cron 调度

架构：
  core/signin.py              — SigninBase 基类 + 注册中心（加载为 core_signin 模块）
  plugins/signin_*.py         — 各平台签到实现（from core_signin import SigninBase, register）
  plugins/forum_signin.py     — 本文件：遍历账号 → 自动匹配插件 → 签到 → 记录日志

扩展：新增论坛签到 → 在 plugins/ 下建 signin_xxx.py，
      继承 SigninBase + @register 即可自动生效。
"""
import sys, os, json, importlib.util as _iu
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
os.environ["FLASHSLOT_SKIP_AUTH"] = "1"

import sqlite3

# ─── 预先加载 core/signin.py 注册为 core_signin 模块 ─────
# 这样做 signin_*.py 插件可以 from core_signin import ... 共享同一个 registry
_core_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "signin.py")
_spec = _iu.spec_from_file_location("core_signin", _core_path)
_core_mod = _iu.module_from_spec(_spec)
sys.modules["core_signin"] = _core_mod  # 预注册到 sys.modules
_spec.loader.exec_module(_core_mod)

get_signin_for_account = _core_mod.get_signin_for_account
list_signins = _core_mod.list_signins
SigninBase = _core_mod.SigninBase

# ─── 动态导入所有 signin_*.py 插件 ─────────────────────
_plugins_dir = os.path.join(os.path.dirname(__file__))
for _f in sorted(os.listdir(_plugins_dir)):
    if _f.startswith("signin_") and _f.endswith(".py") and _f != "__init__.py":
        _path = os.path.join(_plugins_dir, _f)
        _name = _f.replace(".py", "")
        _spec2 = _iu.spec_from_file_location(_name, _path)
        _mod = _iu.module_from_spec(_spec2)
        sys.modules[_name] = _mod  # 预注册，应对内部交叉引用
        _spec2.loader.exec_module(_mod)

# 验证注册状态
_available = list_signins()

CST = timezone(timedelta(hours=8))
DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_signin_log_table():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            site_url TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            already_signed INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            message TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def log_signin(account_id, platform, account_name, site_url,
               success, already_signed, error="", message=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO signin_log (account_id, platform, account_name, site_url, success, already_signed, error, message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (account_id, platform, account_name, site_url,
         1 if success else 0, 1 if already_signed else 0,
         error[:200], message[:200])
    )
    conn.commit()
    conn.close()


def main():
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"🦥 签到 — {now}", ""]

    ensure_signin_log_table()

    available = list_signins()
    if not available:
        print("❌ 没有已注册的签到插件")
        return

    lines.append(f"📦 可用签到插件: {len(available)} 个")
    for s in available:
        lines.append(f"   • {s['display_name']} (平台: {s['platform']})")
    lines.append("")

    conn = get_db()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE is_active=1 ORDER BY platform, account_name"
    ).fetchall()
    conn.close()

    if not accounts:
        print("❌ 没有活跃的账号")
        return

    success_count = 0
    skip_count = 0
    fail_count = 0

    for row in accounts:
        account = dict(row)
        account["config"] = json.loads(account.get("config_json", "{}"))
        site_url = account["config"].get("site_url", "")
        site_name = site_url.replace("https://", "").replace("http://", "").split("/")[0]
        label = f"{account['account_name']} ({site_name})"

        plugin = get_signin_for_account(account)
        if not plugin:
            lines.append(f"⏭️ {label} — 无匹配签到插件，跳过")
            skip_count += 1
            continue

        try:
            result = plugin.signin()
            success = result.get("success", False)
            already = result.get("already_signed", False)
            err = result.get("error", "")
            msg = result.get("message", "")

            log_signin(
                account_id=account["id"],
                platform=account["platform"],
                account_name=account["account_name"],
                site_url=site_url,
                success=success,
                already_signed=already,
                error=err,
                message=msg,
            )

            if success:
                success_count += 1
                if already:
                    lines.append(f"ℹ️ {label} — 今天已签到")
                else:
                    lines.append(f"✅ {label} — {msg}")
            else:
                fail_count += 1
                lines.append(f"❌ {label} — {err or '签到失败'}")
        except Exception as e:
            fail_count += 1
            lines.append(f"❌ {label} — 异常: {e}")
            log_signin(
                account_id=account["id"],
                platform=account["platform"],
                account_name=account["account_name"],
                site_url=site_url,
                success=False,
                already_signed=False,
                error=str(e),
            )

    lines.append("")
    lines.append(f"📊 统计: ✅ {success_count} | ⏭️ {skip_count} | ❌ {fail_count} | 总计 {success_count + skip_count + fail_count} 个账号")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
