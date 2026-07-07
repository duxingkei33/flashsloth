"""Shared Flask app instance — imported by all route modules.

This avoids Blueprint namespacing issues with url_for().
All route modules use @app.route directly on this instance.
"""
import os
from flask import Flask, send_from_directory
from flask_login import LoginManager, UserMixin

app = Flask(__name__,
           template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
           static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
           static_url_path="/static")
app.secret_key = os.environ.get("FLASHSLOTH_SECRET") or os.urandom(64).hex()
app.config["DEBUG"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = False  # 生产环境关闭模板热重载，减少磁盘I/O

# 登录管理器
login_manager = LoginManager()
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


# ─── Jinja2 自定义过滤器 ───
@app.template_filter("split")
def jinja_split(value, sep):
    """Template filter: split string by separator."""
    return value.split(sep)


@app.template_filter("from_json")
def from_json_filter(val):
    """Template filter: parse JSON string to Python object."""
    if not val:
        return []
    try:
        import json
        return json.loads(val)
    except Exception:
        return []


# ─── 全局模板上下文（含请求级缓存，减少重复DB查询） ───
_HAS_XIANYU_CACHE: dict[int, bool] = {}
_HAS_XIANYU_TTL: dict[int, float] = {}

@app.context_processor
def inject_global_context():
    """注入所有模板通用的变量（含缓存，避免每页面查询DB）"""
    import json
    import time
    ctx = {}
    try:
        from flask_login import current_user
        if current_user.is_authenticated:
            uid = current_user.id
            now = time.time()
            if uid in _HAS_XIANYU_CACHE and uid in _HAS_XIANYU_TTL and now - _HAS_XIANYU_TTL[uid] < 30:
                ctx["has_xianyu"] = _HAS_XIANYU_CACHE[uid]
            else:
                from flashsloth.core.database import get_db
                conn = get_db()
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM platform_accounts WHERE user_id=? AND platform LIKE '%xianyu%'",
                    (uid,)
                ).fetchone()
                val = (row and row["c"] > 0) if row else False
                conn.close()
                _HAS_XIANYU_CACHE[uid] = val
                _HAS_XIANYU_TTL[uid] = now
                ctx["has_xianyu"] = val
        else:
            ctx["has_xianyu"] = False
    except Exception:
        ctx["has_xianyu"] = False
    return ctx
