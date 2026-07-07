"""
微信公众号 Publisher — 官方 API 存草稿
微信官方 API，稳定可靠。仅支持存草稿，需在手机上点发布。

v4.57 - Added: image upload to WeChat material library, cover image support,
         auto-summary generation, better error handling.
"""
import time, os, logging, hashlib
import requests
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class WeChatPublisher(Publisher):
    name = "wechat"
    display_name = "微信公众号"
    login_methods = [
        {"method": "password", "label": "API 密钥认证", "icon": "🔑", "priority": 1,
         "fields": ["app_id", "app_secret"],
         "description": "使用微信公众号的 AppID + AppSecret 通过官方 API 认证"},
    ]
    config_fields = [
        {"key": "app_id", "label": "AppID", "type": "text", "required": True},
        {"key": "app_secret", "label": "AppSecret", "type": "password", "required": True},
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self._token = None
        self._token_expires = 0
        self.logger = logging.getLogger(f"publisher.{self.name}")

    def _get_access_token(self) -> str:
        """获取/刷新 access_token"""
        if self._token and time.time() < self._token_expires:
            return self._token
        resp = requests.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": self.config.get("app_id", ""),
                "secret": self.config.get("app_secret", ""),
            },
            timeout=10,
        )
        data = resp.json()
        if "access_token" not in data:
            raise PublishError(f"微信 token 获取失败: {data.get('errmsg', '未知错误')}")
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 7200) - 300
        return self._token

    def _upload_image(self, image_path: str) -> str:
        """上传图片到微信素材库，返回图片 URL（mmbiz.qpic.cn 格式）
        
        返回的 URL 可以直接插入到文章 HTML 的 <img> 标签中。
        """
        token = self._get_access_token()
        if not os.path.exists(image_path):
            raise PublishError(f"图片文件不存在: {image_path}")

        with open(image_path, "rb") as f:
            resp = requests.post(
                "https://api.weixin.qq.com/cgi-bin/material/add_material",
                params={"access_token": token, "type": "image"},
                files={"media": (os.path.basename(image_path), f, "image/png")},
                timeout=60,
            )
        data = resp.json()
        if data.get("errcode", 0) != 0:
            raise PublishError(f"微信图片上传失败: {data.get('errmsg', '未知错误')}")
        
        # 返回永久素材的 URL（mmbiz.qpic.cn 域名）
        return data.get("url", "")

    def validate_config(self) -> list:
        """验证配置完整性"""
        missing = []
        for field in ["app_id", "app_secret"]:
            if not self.config.get(field):
                missing.append(field)
        return missing

    def publish(self, article: Article, **kwargs) -> dict:
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        try:
            token = self._get_access_token()

            # 1. 构建正文 HTML，上传本地图片到微信素材库
            html = article.to_html()
            if hasattr(article, "images") and article.images:
                for img in article.images:
                    local_path = img.get("src", "")
                    if local_path and os.path.exists(local_path):
                        try:
                            wechat_url = self._upload_image(local_path)
                            if wechat_url:
                                # 替换正文中的本地图片引用
                                basename = os.path.basename(local_path)
                                html = html.replace(basename, wechat_url)
                                html = html.replace(local_path, wechat_url)
                                self.logger.info(f"  Uploaded image: {basename} -> WeChat CDN")
                        except Exception as e:
                            self.logger.warning(f"  Image upload failed for {local_path}: {e}")

            # 2. 处理摘要
            digest = (article.summary or "")
            if not digest:
                # 从正文提取纯文本前 120 字
                import re
                text_only = re.sub(r'<[^>]+>', '', html).strip()
                digest = text_only[:120].replace('\n', ' ')

            # 3. 构建图文消息
            body = {
                "title": article.title,
                "content": html,
                "digest": digest[:120],
                "need_open_comment": 0,
                "only_fans_can_comment": 0,
                "content_source_url": article.url or "",
            }

            # 4. 处理封面图
            if hasattr(article, "cover") and article.cover:
                cover_path = article.cover
                if isinstance(cover_path, str) and os.path.exists(cover_path):
                    try:
                        cover_url = self._upload_image(cover_path)
                        if cover_url:
                            body["thumb_media_id"] = cover_url
                    except Exception as e:
                        self.logger.warning(f"  Cover upload failed: {e}")

            # 5. 创建草稿
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
                "status": "draft",
                "note": "草稿已存入公众号，请在手机上点发布",
            }

        except Exception as e:
            return {"success": False, "error": f"发布异常: {e}", "url": "", "id": ""}

    def test_connection(self) -> dict:
        """测试 API 连接有效性"""
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "status": "未配置"}
        try:
            token = self._get_access_token()
            return {
                "success": True,
                "status": f"✅ 已登录 — 已获取 access_token (有效期 2 小时)",
                "token_prefix": token[:8] + "...",
            }
        except Exception as e:
            return {
                "success": False,
                "status": f"❌ 连接失败: {e}",
                "error": str(e),
            }
