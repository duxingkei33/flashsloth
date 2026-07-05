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
app.config["TEMPLATES_AUTO_RELOAD"] = True

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
