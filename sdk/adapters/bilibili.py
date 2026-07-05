"""
哔哩哔哩 SDK 适配器（预留）

提供 B站 API 的基础封装，用于账号状态检测、内容采集等功能。
当前版本为框架预留，完整实现需接入 B站开放平台 API。

注意：B站 Web API 有风控限制，建议配合 Playwright 使用。
"""
from flashsloth.sdk import PlatformAdapter, register


@register
class BilibiliAdapter(PlatformAdapter):
    """哔哩哔哩平台适配器（预留）"""
    name = "bilibili"
    display_name = "哔哩哔哩（预留）"
    description = "B站专栏文章发布 + 视频投稿（预留）"
    config_fields = [
        {"key": "cookie", "label": "B站 Cookie", "type": "password", "required": False,
         "placeholder": "浏览器 F12 获取 Cookie"},
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.cookie = (config or {}).get("cookie", "")

    def test_connection(self) -> dict:
        """测试 B站 Cookie 是否有效（预留）"""
        if not self.cookie:
            return {"success": False, "error": "未配置 Cookie"}
        return {"success": False, "error": "B站适配器开发中（预留），将在后续版本完善"}

    def read(self, url: str) -> dict:
        """读取 B站专栏文章内容（预留）"""
        return {"success": False, "error": "B站内容读取功能开发中（预留）"}

    def post(self, content: dict) -> dict:
        """发布内容到 B站（由 Publisher 实现发布，此方法为预留）"""
        return {"success": False, "error": "B站发布功能开发中（预留），请使用发布页面的哔哩哔哩选项"}

    def list(self, params: dict = None) -> list:
        """列出 B站专栏/视频列表（预留）"""
        return []
