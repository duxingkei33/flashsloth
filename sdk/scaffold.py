"""
SDK 脚手架 — 一键生成新平台适配器

用法:
    from sdk import scaffold_adapter
    scaffold_adapter("weibo", "微博", "https://weibo.com")
    
或命令行:
    python -m sdk.scaffold weibo 微博 https://weibo.com
    
生成文件:
    sdk/adapters/weibo.py
    包含所有9种能力方法的模板，不支持的返回 {"supported": False}
"""
import os
from datetime import datetime
from typing import Optional

ADAPTER_TEMPLATE = '''"""
{display_name} ({site_url}) 平台适配器

能力清单：
  - sign_in()             签到（TODO / 不支持）
  - publish()             发布（TODO / 不支持）
  - retract()             撤回（TODO / 不支持）
  - fetch_posts()         采集帖子（TODO / 不支持）
  - fetch_replies()       采集回复（TODO / 不支持）
  - fetch_thread_detail() 读帖详情（TODO / 不支持）
  - reply_comment()       回复评论（TODO / 不支持）
  - browse_forum()        逛论坛（TODO / 不支持）
  - deploy()              部署（TODO / 不支持）
"""
from typing import Optional
from ..adapter import PlatformAdapter, register, Article, Comment


@register
class {class_name}Adapter(PlatformAdapter):
    name = "{name}"
    display_name = "{display_name}"
    site_url = "{site_url}"
    version = "1.0.0"
    description = "{display_name} — TODO: 添加平台描述"
    icon = "🌐"

    config_fields = [
        # TODO: 添加配置字段
        {{
            "key": "cookie",
            "label": "Cookie",
            "type": "password",
            "required": True,
            "placeholder": "登录后从浏览器 F12 复制 Cookie",
        }},
        {{
            "key": "username",
            "label": "用户名",
            "type": "text",
            "required": False,
        }},
        {{
            "key": "password",
            "label": "密码",
            "type": "password",
            "required": False,
        }},
    ]

    # ─── 签到 ─────────────────────────────────
    def sign_in(self, check_only: bool = False) -> dict:
        """TODO: 实现每日签到"""
        return {{"supported": False}}

    # ─── 发布 ─────────────────────────────────
    def publish(self, article: Article, **kwargs) -> dict:
        """TODO: 实现发布内容到 {display_name}"""
        return {{"supported": False}}

    # ─── 撤回 ─────────────────────────────────
    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """TODO: 实现撤回已发布的内容"""
        return {{"supported": False}}

    # ─── 采集帖子 ─────────────────────────────
    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """TODO: 实现从 {display_name} 采集新内容"""
        return []

    # ─── 采集回复 ─────────────────────────────
    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """TODO: 实现采集评论/回复"""
        return []

    # ─── 读帖详情 ─────────────────────────────
    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """TODO: 实现获取单篇内容详情"""
        return None

    # ─── 回复评论 ─────────────────────────────
    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """TODO: 实现自动回复评论"""
        return {{"supported": False}}

    # ─── 逛论坛 ───────────────────────────────
    def browse_forum(self, **kwargs) -> dict:
        """TODO: 实现浏览/推荐感兴趣的内容"""
        return {{"supported": False}}

    # ─── 部署 ─────────────────────────────────
    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        """TODO: 实现站点部署"""
        return {{"supported": False}}
'''


def scaffold_adapter(name: str, display_name: str, site_url: str) -> str:
    """
    生成新平台适配器文件。
    
    参数:
        name: 平台唯一标识（小写英文，如 "weibo"）
        display_name: 显示名称（如 "微博"）
        site_url: 网站地址（如 "https://weibo.com"）
    
    返回: 生成的适配器文件路径
    """
    # 确保适配器目录存在
    adapters_dir = os.path.join(os.path.dirname(__file__), "adapters")
    os.makedirs(adapters_dir, exist_ok=True)

    # 类名: 首字母大写 + Adapter
    class_name = name.title().replace("_", "").replace("-", "")

    content = ADAPTER_TEMPLATE.format(
        name=name.lower(),
        display_name=display_name,
        site_url=site_url.rstrip("/"),
        class_name=class_name,
    )

    filepath = os.path.join(adapters_dir, f"{name.lower()}.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # 更新 adapters/__init__.py 导入
    init_path = os.path.join(adapters_dir, "__init__.py")
    init_line = f"from .{name.lower()} import {class_name}Adapter  # noqa\n"
    if os.path.exists(init_path):
        with open(init_path, "r") as f:
            existing = f.read()
        if name.lower() not in existing:
            with open(init_path, "a") as f:
                f.write(init_line)
    else:
        with open(init_path, "w") as f:
            f.write(init_line)

    return filepath


def list_scaffolded() -> list[dict]:
    """列出所有已生成的适配器"""
    adapters_dir = os.path.join(os.path.dirname(__file__), "adapters")
    if not os.path.isdir(adapters_dir):
        return []
    result = []
    for f in sorted(os.listdir(adapters_dir)):
        if f.endswith(".py") and f != "__init__.py":
            filepath = os.path.join(adapters_dir, f)
            with open(filepath) as fh:
                content = fh.read()
            has_register = "@register" in content
            todo_count = content.count("TODO:")
            supported_count = content.count('"supported": False')
            result.append({
                "name": f.replace(".py", ""),
                "file": f,
                "registered": has_register,
                "todos": todo_count,
                "unsupported": supported_count,
            })
    return result


def main():
    """CLI入口"""
    import sys
    if len(sys.argv) < 4:
        print("用法: python -m sdk.scaffold <name> <display_name> <site_url>")
        print("示例: python -m sdk.scaffold weibo 微博 https://weibo.com")
        sys.exit(1)

    name = sys.argv[1]
    display_name = sys.argv[2]
    site_url = sys.argv[3]

    filepath = scaffold_adapter(name, display_name, site_url)
    print(f"✅ 适配器已创建: {filepath}")
    print(f"   name: {name}")
    print(f"   display_name: {display_name}")
    print(f"   site_url: {site_url}")
    print()
    print("下一步:")
    print(f"  1. 编辑 {filepath}")
    print(f"  2. 实现需要的能力方法（去掉 TODO:）")
    print(f"  3. 不支持的保持返回 {{\"supported\": False}}")
    print(f"  4. 在 admin.py 中添加 import，或使用 from sdk.adapters.{name} import ...")
    print()
    print("参考: sdk/adapters/mydigit.py（完整实现示例）")


if __name__ == "__main__":
    main()
