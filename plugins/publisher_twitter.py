"""
Twitter/X Publisher — 通过 tweepy 使用官方 API v2 发布
支持 OAuth 1.0a 用户上下文认证（发推+图片上传）

依赖: tweepy>=4.14
安装: pip install tweepy

功能介绍:
  - 推文发布（单条或线程）
  - 图片上传（最多 4 张）
  - 存草稿（本地缓存，Twitter 无草稿概念）
  - 使用 Compiler Engine 的 plain text 编译规则

注意:
  - 需要 Twitter Developer Portal 创建应用获取 API Key/Secret
  - 需要开启 OAuth 1.0a 才能发推
  - 图片通过 media/upload (API v1.1) 上传后挂载到推文
"""
import os, json, time, datetime
import tweepy
from typing import Optional
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


@register
class TwitterPublisher(Publisher):
    name = "twitter"
    display_name = "Twitter / X"
    login_methods = [
        {
            "method": "oauth1",
            "label": "OAuth 1.0a 认证",
            "icon": "🔑",
            "priority": 1,
            "fields": ["api_key", "api_secret", "access_token", "access_token_secret"],
            "description": "使用 Twitter API v2 OAuth 1.0a 认证（推荐，可发推+上传图片）",
        },
        {
            "method": "bearer",
            "label": "Bearer Token (只读)",
            "icon": "🔒",
            "priority": 2,
            "fields": ["bearer_token"],
            "description": "仅使用 Bearer Token（只读，用于验证连接和查询账户信息）",
        },
    ]
    config_fields = [
        {"key": "api_key", "label": "API Key (Consumer Key)", "type": "text",
         "required": False, "placeholder": "Twitter Developer Portal 中的 API Key"},
        {"key": "api_secret", "label": "API Secret (Consumer Secret)", "type": "password",
         "required": False, "placeholder": "Twitter Developer Portal 中的 API Secret"},
        {"key": "access_token", "label": "Access Token", "type": "password",
         "required": False, "placeholder": "用户 Access Token"},
        {"key": "access_token_secret", "label": "Access Token Secret", "type": "password",
         "required": False, "placeholder": "用户 Access Token Secret"},
        {"key": "bearer_token", "label": "Bearer Token", "type": "password",
         "required": False, "placeholder": "仅用于只读模式"},
        {"key": "max_tweet_length", "label": "推文长度上限", "type": "number",
         "required": False, "default": 280,
         "placeholder": "280（普通用户）或 4000（X Premium 用户）"},
        {"key": "as_thread", "label": "超长内容自动拆线程", "type": "select",
         "options": ["true", "false"], "default": "true",
         "description": "内容超出一推长度时，自动拆分为多条推文的线程"},
    ]

    # Twitter/X 平台限制
    PLATFORM_LIMITS = {
        "max_images": 4,
        "max_tweet_length": 280,
        "max_thread_length": 50,  # 单线程最多 50 条
        "supported_formats": ('.jpg', '.jpeg', '.png', '.gif', '.webp'),
        "max_image_size": 5 * 1024 * 1024,  # 5MB
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.access_token = config.get("access_token", "")
        self.access_token_secret = config.get("access_token_secret", "")
        self.bearer_token = config.get("bearer_token", "")
        self.max_tweet_length = int(config.get("max_tweet_length", 280))
        self.as_thread = config.get("as_thread", "true") == "true"
        self._client = None

    def _get_client(self):
        """初始化并缓存 tweepy Client"""
        if self._client is not None:
            return self._client

        if self.access_token and self.access_token_secret:
            # OAuth 1.0a 用户上下文（读写）
            auth = tweepy.OAuth1UserHandler(
                self.api_key, self.api_secret,
                self.access_token, self.access_token_secret,
            )
            self._client = tweepy.Client(
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_token_secret,
            )
            self._api_v1 = tweepy.API(auth)  # 用于 media/upload (v1.1)
        elif self.bearer_token:
            # Bearer Token 只读模式
            self._client = tweepy.Client(bearer_token=self.bearer_token)
            self._api_v1 = None
        else:
            raise PublishError("Twitter 认证信息不完整：需要 OAuth 1.0a 或 Bearer Token")

        return self._client

    def validate_config(self) -> list[str]:
        """验证配置完整性"""
        missing = []
        auth_mode = self.config.get("login_mode", "oauth1")
        if auth_mode == "oauth1":
            if not self.api_key:
                missing.append("API Key")
            if not self.api_secret:
                missing.append("API Secret")
            if not self.access_token:
                missing.append("Access Token")
            if not self.access_token_secret:
                missing.append("Access Token Secret")
        elif auth_mode == "bearer":
            if not self.bearer_token:
                missing.append("Bearer Token")
        return missing

    def test_connection(self) -> dict:
        """测试 Twitter API 连接 — 获取当前用户信息"""
        try:
            client = self._get_client()
            # 获取自己的用户信息来验证认证
            me = client.get_me(user_auth=bool(self.access_token))
            if me.data:
                return {
                    "success": True,
                    "error": "",
                    "status": f"已认证: @{me.data.username} (ID: {me.data.id})",
                }
            return {"success": False, "error": "无法获取用户信息", "status": "认证失败"}
        except Exception as e:
            return {"success": False, "error": f"连接失败: {e}", "status": "异常"}

    def upload_image(self, local_path: str) -> dict:
        """上传图片到 Twitter（使用 API v1.1 media/upload）"""
        if not os.path.isfile(local_path):
            return {"success": False, "url": "", "error": f"文件不存在: {local_path}"}

        if not self._api_v1:
            return {"success": False, "url": "", "error": "OAuth 1.0a 未配置，无法上传图片"}

        try:
            # 检查文件格式
            ext = os.path.splitext(local_path)[1].lower()
            if ext not in self.PLATFORM_LIMITS["supported_formats"]:
                return {
                    "success": False, "url": "", "error":
                    f"不支持的格式 {ext}，支持: {', '.join(self.PLATFORM_LIMITS['supported_formats'])}"
                }

            # 检查文件大小
            size = os.path.getsize(local_path)
            if size > self.PLATFORM_LIMITS["max_image_size"]:
                return {
                    "success": False, "url": "", "error":
                    f"图片过大 ({size/1024/1024:.1f}MB > {self.PLATFORM_LIMITS['max_image_size']/1024/1024:.0f}MB)"
                }

            # 上传到 Twitter
            media = self._api_v1.media_upload(filename=local_path)
            return {
                "success": True,
                "url": f"https://twitter.com/i/web/status/{media.media_id_string}",
                "media_id": media.media_id_string,
            }
        except Exception as e:
            return {"success": False, "url": "", "error": f"上传异常: {str(e)[:200]}"}

    def _split_into_tweets(self, text: str) -> list[str]:
        """将长文本拆分为多条推文（线程）"""
        max_len = self.max_tweet_length
        if len(text) <= max_len:
            return [text]

        tweets = []
        paragraphs = text.split("\n\n")
        current = ""

        for para in paragraphs:
            # 如果单段超长，按句子拆分
            if len(para) > max_len:
                if current:
                    tweets.append(current)
                    current = ""
                # 按句号拆分
                sentences = para.replace("。", ".。").split(".")
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if len(current) + len(sent) + 2 <= max_len:
                        current = f"{current}\n\n{sent}".strip() if current else sent
                    else:
                        if current:
                            tweets.append(current)
                        # 单句也超长 → 硬截断
                        current = sent[:max_len - 3] + "..." if len(sent) > max_len else sent
                continue

            if len(current) + len(para) + 2 <= max_len:
                current = f"{current}\n\n{para}".strip() if current else para
            else:
                tweets.append(current)
                current = para

        if current:
            tweets.append(current)

        return tweets

    def publish(self, article: Article, **kwargs) -> dict:
        """
        发布推文（或线程）到 Twitter/X

        kwargs:
            mode: "publish" | "draft" (draft = 本地缓存，不发)
            as_thread: True = 超长内容自动拆线程
            media_ids: 预上传的 media_id 列表
        """
        missing = self.validate_config()
        if missing:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        save_as_draft = kwargs.get("save_as_draft", False)
        as_thread = kwargs.get("as_thread", self.as_thread)

        try:
            client = self._get_client()

            # 从 article 获取推文内容
            body = article.body or ""
            # 编译系统应已处理格式转换，但确保是纯文本
            title = article.title or ""

            # 构建推文文本：标题 + 正文
            tweet_text = body
            if title and not body.startswith(title):
                tweet_text = f"{title}\n\n{body}"

            # 提取图片 media_ids
            media_ids = kwargs.get("media_ids", [])
            # 如果 kwargs 中没有，尝试从 article.images 读取
            if not media_ids and hasattr(article, "images") and article.images:
                for img in article.images:
                    if isinstance(img, dict) and img.get("uploaded_url"):
                        media_ids.append(img["uploaded_url"])

            if save_as_draft:
                # Twitter 无草稿概念 → 保存到本地文件
                draft_dir = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "drafts", "twitter"
                )
                os.makedirs(draft_dir, exist_ok=True)
                draft = {
                    "title": title,
                    "body": tweet_text,
                    "media_ids": media_ids,
                    "as_thread": as_thread,
                    "created_at": datetime.datetime.now().isoformat(),
                }
                draft_path = os.path.join(
                    draft_dir,
                    f"draft_{int(time.time())}.json"
                )
                with open(draft_path, "w", encoding="utf-8") as f:
                    json.dump(draft, f, ensure_ascii=False, indent=2)
                return {
                    "success": True,
                    "url": "",
                    "id": "",
                    "error": "",
                    "message": f"草稿已保存到 {draft_path}",
                    "draft_path": draft_path,
                }

            # 实际发布 — 按线程或多推拆分
            if as_thread and len(tweet_text) > self.max_tweet_length:
                tweets = self._split_into_tweets(tweet_text)
                return self._publish_thread(client, tweets, media_ids)
            else:
                return self._publish_single(client, tweet_text, media_ids)

        except Exception as e:
            return {"success": False, "error": f"Twitter 发布异常: {e}",
                    "url": "", "id": ""}

    def _publish_single(self, client, text: str, media_ids: list = None) -> dict:
        """发布单条推文"""
        params = {"text": text[:self.max_tweet_length]}
        if media_ids:
            params["media_ids"] = media_ids[:4]

        try:
            response = client.create_tweet(**params, user_auth=True)
            if response.data and response.data.get("id"):
                tweet_id = response.data["id"]
                return {
                    "success": True,
                    "url": f"https://twitter.com/i/web/status/{tweet_id}",
                    "id": tweet_id,
                    "error": "",
                }
            return {"success": False, "error": f"推文发布失败: {response.errors}",
                    "url": "", "id": ""}
        except Exception as e:
            return {"success": False, "error": f"推文发布异常: {e}",
                    "url": "", "id": ""}

    def _publish_thread(self, client, tweets: list[str], media_ids: list = None) -> dict:
        """发布线程（多条回复推文）"""
        if not tweets:
            return {"success": False, "error": "没有内容可发布", "url": "", "id": ""}

        published_ids = []
        media_idx = 0

        for i, tweet_text in enumerate(tweets):
            params = {"text": tweet_text[:self.max_tweet_length]}

            # 图片：只在第一条推文附加（Twitter 线程通常只有主推有图）
            if i == 0 and media_ids:
                params["media_ids"] = media_ids[:4]

            # 回复上一条（形成线程）
            if published_ids:
                params["in_reply_to_tweet_id"] = published_ids[-1]

            try:
                response = client.create_tweet(**params, user_auth=True)
                if response.data and response.data.get("id"):
                    published_ids.append(response.data["id"])
                else:
                    break
            except Exception:
                break

            # 线程间礼貌间隔
            time.sleep(2)

        if not published_ids:
            return {"success": False, "error": "线程发布失败，首条推文未发出",
                    "url": "", "id": ""}

        return {
            "success": True,
            "url": f"https://twitter.com/i/web/status/{published_ids[0]}",
            "id": ",".join(published_ids),
            "thread_ids": published_ids,
            "tweet_count": len(published_ids),
            "error": "",
        }

    def retract(self, article: Article, publish_log: dict = None) -> dict:
        """删除已发布的推文"""
        if not publish_log or not publish_log.get("id"):
            return {"success": False, "error": "缺少发布记录", "message": ""}

        try:
            client = self._get_client()
            ids = publish_log["id"].split(",")
            deleted = []
            failed = []

            for tid in ids:
                try:
                    client.delete_tweet(id=int(tid), user_auth=True)
                    deleted.append(tid)
                except Exception as e:
                    failed.append((tid, str(e)))

            if not failed:
                return {
                    "success": True,
                    "error": "",
                    "message": f"已删除 {len(deleted)} 条推文",
                }
            return {
                "success": False,
                "error": f"部分删除失败: {len(failed)}/{len(ids)}",
                "message": f"成功: {len(deleted)}, 失败: {len(failed)}",
            }
        except Exception as e:
            return {"success": False, "error": f"删除异常: {e}", "message": ""}
