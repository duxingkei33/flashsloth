"""
FlashSloth Unified API v1 — 标准化开放接口层
============================================

所有功能以统一 REST 风格暴露，供外部系统/AI skill 调用。

鉴权方式:
  Authorization: Bearer <api_key>
  或 X-API-Key: <api_key>

返回格式:
  {
    "success": true|false,
    "data": { ... },       // 成功时
    "error": "..."         // 失败时
  }

API Key 管理:
  - 在 /settings 页面生成/管理 API Key
  - 每个 Key 关联到对应的用户
"""
import json, os, time, hashlib, secrets, hmac
from datetime import datetime

from flask import request, jsonify, g
from flask_login import login_required, current_user

from flashsloth.routes._app import app
from flashsloth.core.database import get_db
from flashsloth.core.ai_provider import get_router, AIRequest


# ═══════════════════════════════════════════════
# API Key 鉴权
# ═══════════════════════════════════════════════

_API_KEY_CACHE: dict[str, int] = {}  # key -> user_id


def _init_api_keys_table():
    """确保 api_keys 表存在"""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT 'default',
            key_hash TEXT NOT NULL,
            key_prefix TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            last_used_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(key_prefix);
        CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
    """)
    conn.commit()
    conn.close()


def _verify_api_key(key: str) -> int | None:
    """验证 API Key，返回 user_id 或 None"""
    if not key or len(key) < 16:
        return None
    prefix = key[:12]
    conn = get_db()
    row = conn.execute(
        "SELECT user_id, key_hash FROM api_keys WHERE key_prefix=? AND is_active=1",
        (prefix,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    expected_hash = hashlib.sha256(key.encode()).hexdigest()
    if hmac.compare_digest(expected_hash, row["key_hash"]):
        # 更新最后使用时间（异步友好）
        try:
            conn2 = get_db()
            conn2.execute(
                "UPDATE api_keys SET last_used_at=datetime('now') WHERE key_prefix=?",
                (prefix,)
            )
            conn2.commit()
            conn2.close()
        except Exception:
            pass
        return row["user_id"]
    return None


def require_api_key(f):
    """装饰器：支持 Web session 或 API Key 鉴权"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        # 优先用 Web session（已登录）
        if hasattr(g, 'login_disabled') and g.login_disabled:
            pass
        try:
            from flask_login import current_user
            if current_user and current_user.is_authenticated:
                g.api_user_id = current_user.id
                return f(*args, **kwargs)
        except Exception:
            pass

        # 检查 API Key
        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")

        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

        if not api_key:
            return jsonify({"success": False, "error": "缺少 API Key。请使用 Authorization: Bearer <key> 或 X-API-Key: <key>"}), 401

        user_id = _verify_api_key(api_key)
        if user_id is None:
            return jsonify({"success": False, "error": "API Key 无效或已禁用"}), 401

        g.api_user_id = user_id
        return f(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════

def ok(data=None, message=""):
    """统一成功响应"""
    resp = {"success": True}
    if data is not None:
        resp["data"] = data
    if message:
        resp["message"] = message
    return jsonify(resp)


def fail(error, code=400):
    """统一失败响应"""
    return jsonify({"success": False, "error": error}), code


# ═══════════════════════════════════════════════
# API Key 管理端点（Web session 保护）
# ═══════════════════════════════════════════════

@app.route("/api/v1/keys", methods=["GET"])
@login_required
def api_v1_list_keys():
    """列出当前用户的 API Keys"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, key_prefix, is_active, last_used_at, created_at FROM api_keys WHERE user_id=? ORDER BY created_at DESC",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return ok([dict(r) for r in rows])


@app.route("/api/v1/keys", methods=["POST"])
@login_required
def api_v1_create_key():
    """创建新的 API Key（返回完整 key，仅一次）"""
    data = request.get_json() or {}
    name = data.get("name", "").strip() or f"key-{secrets.token_hex(4)}"

    key = f"sf_{secrets.token_hex(24)}"  # sf_ + 48字符 hex = 51字符
    prefix = key[:12]
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    conn = get_db()
    conn.execute(
        "INSERT INTO api_keys (user_id, name, key_hash, key_prefix) VALUES (?, ?, ?, ?)",
        (current_user.id, name, key_hash, prefix)
    )
    key_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()

    return ok({
        "id": key_id,
        "name": name,
        "key": key,
        "key_prefix": prefix,
    }, "API Key 创建成功！请立即保存，再次显示将不可见。")


@app.route("/api/v1/keys/<int:kid>/toggle", methods=["POST"])
@login_required
def api_v1_toggle_key(kid):
    """启用/禁用 API Key"""
    conn = get_db()
    row = conn.execute(
        "SELECT is_active FROM api_keys WHERE id=? AND user_id=?",
        (kid, current_user.id)
    ).fetchone()
    if not row:
        conn.close()
        return fail("API Key 不存在", 404)
    new_val = 0 if row["is_active"] else 1
    conn.execute("UPDATE api_keys SET is_active=? WHERE id=?", (new_val, kid))
    conn.commit()
    conn.close()
    return ok({"is_active": bool(new_val)})


@app.route("/api/v1/keys/<int:kid>", methods=["DELETE"])
@login_required
def api_v1_delete_key(kid):
    """删除 API Key"""
    conn = get_db()
    conn.execute("DELETE FROM api_keys WHERE id=? AND user_id=?", (kid, current_user.id))
    conn.commit()
    deleted = conn.total_changes > 0
    conn.close()
    if not deleted:
        return fail("API Key 不存在", 404)
    return ok(message="已删除")


# ═══════════════════════════════════════════════
# 系统状态
# ═══════════════════════════════════════════════

@app.route("/api/v1/status", methods=["GET"])
@require_api_key
def api_v1_status():
    """系统状态概览"""
    uid = g.api_user_id
    conn = get_db()
    accounts = conn.execute(
        "SELECT COUNT(*) as total, SUM(is_active) as active FROM platform_accounts WHERE user_id=?", (uid,)
    ).fetchone()
    articles = conn.execute(
        "SELECT COUNT(*) as total FROM articles WHERE user_id=?", (uid,)
    ).fetchone()
    ai_configs = conn.execute(
        "SELECT COUNT(*) as total FROM ai_configs WHERE user_id=?", (uid,)
    ).fetchone()
    conn.close()

    return ok({
        "version": "4.2.0",
        "name": "FlashSloth",
        "accounts": {
            "total": accounts["total"],
            "active": accounts["active"] or 0,
        },
        "articles": {
            "total": articles["total"],
        },
        "ai_configs": {
            "total": ai_configs["total"],
        },
        "capabilities": list(get_router()._capability_configs.keys()),
    })


# ═══════════════════════════════════════════════
# AI 生成
# ═══════════════════════════════════════════════

@app.route("/api/v1/ai/generate", methods=["POST"])
@require_api_key
def api_v1_ai_generate():
    """AI 文章生成

    请求体:
    {
        "prompt": "写一篇关于...的文章",
        "capability": "writing",        # 可选，默认 writing
        "provider": "deepseek",          # 可选，覆盖能力路由
        "model": "deepseek-chat",        # 可选，覆盖模型
        "mode": "chat",                  # chat | competition
        "temperature": 0.7,              # 可选
    }
    """
    data = request.get_json() or {}
    prompt = data.get("prompt", "")
    if not prompt:
        return fail("缺少 prompt 参数")

    capability = data.get("capability", "writing")
    provider = data.get("provider", "")
    model = data.get("model", "")
    mode = data.get("mode", "chat")
    temperature = data.get("temperature", 0.7)

    router = get_router()
    ai_req = AIRequest(
        prompt=prompt,
        capability=capability,
        provider=provider or None,
        model=model or None,
        mode=mode,
        temperature=temperature,
    )

    try:
        result = router.call(ai_req) if mode != "competition" else router.call_parallel(capability, [prompt])
        if hasattr(result, 'success') and not result.success:
            return fail(result.error or "AI 生成失败", 500)
        if isinstance(result, list):
            texts = [r.text if hasattr(r, 'text') else str(r) for r in result]
            return ok({"texts": texts, "provider": provider or "auto"})
        text = result.text if hasattr(result, 'text') else str(result)
        return ok({"text": text, "provider": provider or "auto"})
    except Exception as e:
        return fail(f"AI 生成异常: {e}", 500)


# ═══════════════════════════════════════════════
# 账号
# ═══════════════════════════════════════════════

@app.route("/api/v1/accounts", methods=["GET"])
@require_api_key
def api_v1_accounts_list():
    """获取账号列表"""
    uid = g.api_user_id
    conn = get_db()
    rows = conn.execute(
        "SELECT id, platform, account_name, status, is_active, created_at FROM platform_accounts WHERE user_id=? ORDER BY platform",
        (uid,)
    ).fetchall()
    conn.close()
    return ok([dict(r) for r in rows])


@app.route("/api/v1/accounts/test", methods=["POST"])
@require_api_key
def api_v1_accounts_test():
    """测试账号连接状态"""
    data = request.get_json() or {}
    aid = data.get("account_id")
    if not aid:
        return fail("缺少 account_id")

    # 复用 routes/accounts.py 的内部逻辑
    from flashsloth.routes.accounts import api_account_status
    # 需要模拟 current_user
    from flask_login import login_user
    uid = g.api_user_id
    conn = get_db()
    user_row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    if not user_row:
        return fail("用户不存在", 404)

    from flashsloth.routes._app import User
    fake_user = User(user_row)

    # 临时登录以调用受保护路由
    from flask import g as flask_g
    old_user = getattr(flask_g, 'api_user_id', None)
    # 直接查询并返回
    return _direct_account_status(aid, uid)


def _direct_account_status(aid, uid):
    """直接检查账号状态（不经过 Flask login）"""
    import requests as _req
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, uid)
    ).fetchone()
    conn.close()
    if not acct:
        return fail("账号不存在", 404)
    acct = dict(acct)
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    site_url = cfg.get("site_url", "")
    cookie = cfg.get("cookie", "")
    return ok({
        "platform": acct["platform"],
        "account_name": acct["account_name"],
        "has_cookie": bool(cookie),
        "site_url": site_url,
        "status": "已配置" if cookie else "未配置Cookie",
    })


# ═══════════════════════════════════════════════
# 签到
# ═══════════════════════════════════════════════

@app.route("/api/v1/signin/run", methods=["POST"])
@require_api_key
def api_v1_signin_run():
    """执行签到"""
    data = request.get_json() or {}
    account_id = data.get("account_id")

    # 直接调用内部签到逻辑
    from flashsloth.routes.signin import api_signin_account
    uid = g.api_user_id

    # 因 api_signin_account 需要 current_user，我们用函数包装
    conn = get_db()
    if account_id:
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
            (account_id, uid)
        ).fetchone()
    else:
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE user_id=? AND is_active=1 LIMIT 1",
            (uid,)
        ).fetchone()
    conn.close()

    if not acct:
        return fail("没有可签到的账号", 404)

    acct = dict(acct)
    from flashsloth.core.signin import get_signin_for_account
    plugin = get_signin_for_account(acct)
    if not plugin:
        return fail(f"账号 {acct['account_name']} 没有匹配的签到插件")

    try:
        result = plugin.signin()
        return ok({
            "account": acct["account_name"],
            "platform": acct["platform"],
            "success": result.get("success", False),
            "message": result.get("message", ""),
        })
    except Exception as e:
        return fail(f"签到失败: {e}", 500)


# ═══════════════════════════════════════════════
# 浏览器登录
# ═══════════════════════════════════════════════

@app.route("/api/v1/browser/login", methods=["POST"])
@require_api_key
def api_v1_browser_login():
    """启动浏览器登录流程"""
    data = request.get_json() or {}
    account_id = data.get("account_id")
    if not account_id:
        return fail("缺少 account_id")

    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (account_id, g.api_user_id)
    ).fetchone()
    conn.close()

    if not acct:
        return fail("账号不存在", 404)

    acct = dict(acct)
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    site_url = cfg.get("site_url", "")

    if not site_url:
        return fail("账号未配置站点 URL")

    return ok({
        "account_id": account_id,
        "platform": acct["platform"],
        "account_name": acct["account_name"],
        "login_url": site_url,
        "note": "请在浏览器中打开 login_url 完成登录",
    })


# ═══════════════════════════════════════════════
# AI 配置
# ═══════════════════════════════════════════════

@app.route("/api/v1/ai/config", methods=["GET"])
@require_api_key
def api_v1_ai_config():
    """获取 AI 能力路由配置"""
    router = get_router()
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT provider, models FROM ai_configs WHERE user_id=? AND enabled=1",
        (g.api_user_id,)
    ).fetchall()
    conn.close()
    provider_models = {}
    for r in rows:
        try:
            models = json.loads(r["models"] or "[]")
            provider_models[r["provider"]] = models
        except Exception:
            provider_models[r["provider"]] = []

    return ok({
        "capabilities": {k: v for k, v in router._capability_configs.items()},
        "provider_models": provider_models,
    })


@app.route("/api/v1/ai/providers", methods=["GET"])
@require_api_key
def api_v1_ai_providers():
    """获取已配置的 AI 供应商列表"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, provider, alias, api_format, models, enabled, balance FROM ai_configs WHERE user_id=? ORDER BY provider",
        (g.api_user_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["models_list"] = json.loads(d.get("models") or "[]")
        except Exception:
            d["models_list"] = []
        result.append(d)
    return ok({"providers": result})


# ═══════════════════════════════════════════════
# 初始化（在应用启动时调用）
# ═══════════════════════════════════════════════

def init_api_v1():
    """初始化 API v1 模块（创建表等）"""
    _init_api_keys_table()
