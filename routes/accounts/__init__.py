"""FlashSloth — 账号管理路由（模块化入口）"""
from flashsloth.routes._app import app
from flask_login import login_required, current_user

# 导入各子模块（触发 @app.route 注册）
import flashsloth.routes.accounts.helpers
import flashsloth.routes.accounts.crud
import flashsloth.routes.accounts.search
import flashsloth.routes.accounts.login
import flashsloth.routes.accounts.qrcode
import flashsloth.routes.accounts.status

# 显式 re-export（供 routes/api_v1.py 引用）
from flashsloth.routes.accounts.status import api_account_status
