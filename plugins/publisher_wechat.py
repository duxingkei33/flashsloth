"""
微信公众号 Publisher — 官方 API 存草稿
微信官方 API，稳定可靠。仅支持存草稿，需在手机上点发布。
"""
import time, requests
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class WeChatPublisher(Publisher):
    name = "wechat"
    display_name = "微信公众号"
    config_fields = [
        {"key": "app_id", "label": "AppID", "type": "text", "required": True},
        {"key": "app_secret", "label": "AppSecret", "type": "password", "required": True},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self._token = None
        self._token_expires = 0

    def _get_access_token(self) -> str:
        """获取/刷新 access_token"""
        if self._token and time.time() < self._token_expires:
            return self._token
        resp = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": self.config["app_id"],
                "secret": self.config["app_secret"],
            },
            timeout=10,
        )
        data = resp.json()
        if "access_token" not in data:
            raise PublishError(f"微信 token 获取失败: {data.get('errmsg', '未知错误')}")
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 7200) - 300
        return self._token

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        try:
            token = self._get_access_token()

            # 构建草稿正文（微信用 HTML）
            html = article.to_html()
            # 微信限制正文不能有外链图片，需先上传图片素材
            # 简化版：直接提交 HTML

            body = {
                "title": article.title,
                "content": html,
                "digest": (article.summary or "")[:120],
                "need_open_comment": 0,
                "only_fans_can_comment": 0,
            }
            if article.cover:
                # 需先上传封面图到微信素材库
                pass

            resp = requests.post(
                "https://api.weixin.qq.com/cgi-bin/draft/add",
                params={"access_token": token},
                json={"articles": [body]},
                timeout=30,
            )
            data = resp.json()
            if data.get("errcode", -1) != 0:
                return {
                    "success": False,
                    "error": f"微信草稿创建失败: {data.get('errmsg', '未知错误')}",
                    "url": "", "id": "",
                }

            media_id = data.get("media_id", "")
            return {
                "success": True,
                "url": "",
                "id": media_id,
                "error": "",
                "note": "草稿已存入公众号，请在手机上点发布",
            }

        except Exception as e:
            return {"success": False, "error": f"发布异常: {e}", "url": "", "id": ""}
