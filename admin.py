"""
FlashSloth Admin — 商用级多平台内容发布后台
入口点：创建应用、初始化、启动

架构:
  routes/          路由模块（Blueprints）
  core/            核心功能（DB、调度器、AI等）
  plugins/         平台适配插件
  sdk/             SDK适配器
  templates/       Jinja2模板
"""
import os, sys

# 确保项目根目录在路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─── 导入插件触发注册 ───
import flashsloth.plugins.publisher_wordpress  # noqa
import flashsloth.plugins.publisher_wechat     # noqa
import flashsloth.plugins.publisher_juejin     # noqa
import flashsloth.plugins.publisher_rss        # noqa
import flashsloth.plugins.publisher_zhihu      # noqa
import flashsloth.plugins.publisher_csdn       # noqa
import flashsloth.plugins.publisher_discuz     # noqa
import flashsloth.plugins.publisher_xianyu     # noqa
import flashsloth.plugins.publisher_github_pages  # noqa
import flashsloth.plugins.publisher_bilibili    # noqa
import flashsloth.plugins.publisher_oshwhub     # noqa
import flashsloth.plugins.publisher_twitter      # noqa 🐦
import flashsloth.plugins.deployer_github_pages  # noqa
import flashsloth.plugins.storage_alist        # noqa
import flashsloth.plugins.forum_reader          # noqa
import flashsloth.plugins.forum_signin           # noqa
import flashsloth.sdk.adapters.mydigit           # noqa
import flashsloth.sdk.adapters.amobbs            # noqa
import flashsloth.sdk.adapters.csdn              # noqa
import flashsloth.sdk.adapters.xianyu            # noqa
import flashsloth.sdk.adapters.notion            # noqa
import flashsloth.sdk.adapters.github_pages      # noqa
import flashsloth.sdk.adapters.bilibili           # noqa
import flashsloth.sdk.adapters.oshwhub           # noqa
import flashsloth.routes.comment_monitor          # noqa 💬

# ─── 创建应用 ───
from flashsloth.routes import configure_app
from flashsloth.routes._app import app, login_manager, User
from flashsloth.core.database import init_db, _get_boot_credentials
from flashsloth.core.scheduler import start_scheduler

configure_app()

# ─── 向后兼容：旧模块可能引用 admin._BOOT_CREDENTIALS ───
_BOOT_CREDENTIALS = _get_boot_credentials()
_signin_scheduler_running = property(lambda self: None)
_signin_scheduler_stop = None
_start_signin_scheduler = start_scheduler


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
    start_scheduler()
    app.run(host=host, port=port, debug=False)
