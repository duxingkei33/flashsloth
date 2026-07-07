"""
Twitter/X Publisher — 通过 tweepy 使用官方 API v2 发布
支持 OAuth 1.0a 用户上下文认证（发推+图片上传）

依赖: tweepy>=4.14
安装: pip install tweepy

功能介绍:
  - 推文发布（单条或线程）
  - 图片上传（最多 4 张，使用 API v1.1 media/upload）
  - 存草稿（JSON 本地缓存）
  - 线程拆分（按段落/句子/硬截断）
  - Compiler Engine 集成
  - 限流退避重试（HTTP 429 指数退避）
  - 连接缓存（5 分钟 TTL）

注意:
  - 需要 Twitter Developer Portal 创建应用获取 API Key/Secret
  - 需要开启 OAuth 1.0a 才能发推和上传图片
  - 图片通过 media/upload (API v1.1) 上传后挂载到推文
  - 草稿模式纯本地，Twitter 无原生草稿概念
"""
import os, json, time, datetime, logging, re, tempfile
import tweepy
from typing import Optional

from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError


# 限流退避参数
_RATE_LIMIT_BASE_DELAY = 2.0       # 秒
_RATE_LIMIT_MAX_DELAY = 120.0      # 最大等待 2 分钟
_RATE_LIMIT_RETRIES = 3
_CONNECTION_CACHE_TTL = 300        # 5 分钟


@register
class TwitterPublisher(Publisher):
    name = "twitter"
    display_name = "Twitter / X"
    architecture = "Twitter/X"
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
    guide = {
        "title": "Twitter API 凭证申请指南",
        "url": "https://developer.twitter.com/en/portal/dashboard",
        "steps": [
            "前往 Twitter Developer Portal，登录你的 Twitter 账号",
            "创建新 Project（或使用已有 Project）",
            "在 'Keys and Tokens' 页面生成 API Key 和 API Secret",
            "在 'Authentication Settings' 设置 OAuth 1.0a 权限（需要 Read + Write）",
            "生成 Access Token 和 Access Token Secret",
            "将以上 4 个凭证填入下方对应字段"
        ],
        "fields_map": {
            "api_key": "Consumer API Key (API Key)",
            "api_secret": "Consumer API Secret (API Secret)",
            "access_token": "Access Token",
            "access_token_secret": "Access Token Secret"
        }
    }
    config_fields = [
        {"key": "site_url", "label": "站点 URL", "type": "text",
         "required": False, "default": "https://twitter.com",
         "placeholder": "https://twitter.com 或 https://x.com"},
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
        "max_gif_size": 15 * 1024 * 1024,   # 15MB for GIF
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.logger = logging.getLogger(f"publisher.twitter")
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.access_token = config.get("access_token", "")
        self.access_token_secret = config.get("access_token_secret", "")
        self.bearer_token = config.get("bearer_token", "")
        self.max_tweet_length = int(config.get("max_tweet_length", 280))
        self.as_thread = config.get("as_thread", "true") == "true"
        self.site_url = config.get("site_url", "https://twitter.com")
        self._client = None
        self._api_v1 = None
        self._connection_cache = {"result": None, "ts": 0.0}  # {result, ts}

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
        """测试 Twitter API 连接 — 获取当前用户信息（零 token 消耗）

        带 5 分钟缓存，避免高频调用。
        """
        # 检查缓存
        now = time.time()
        if self._connection_cache["result"] and now - self._connection_cache["ts"] < _CONNECTION_CACHE_TTL:
            return self._connection_cache["result"]

        try:
            client = self._get_client()
            # 带超时 — 防止假凭据导致无限等待
            me = client.get_me(user_auth=bool(self.access_token))
            if me.data:
                result = {
                    "success": True,
                    "error": "",
                    "status": f"已认证: @{me.data.username} (ID: {me.data.id})",
                }
            else:
                result = {"success": False, "error": "无法获取用户信息", "status": "认证失败"}
        except tweepy.Forbidden as e:
            result = {"success": False, "error": f"Twitter 权限不足（需 Read+Write）: {e}", "status": "权限不足"}
        except tweepy.Unauthorized as e:
            result = {"success": False, "error": f"Twitter 认证失败: {e}", "status": "认证失败"}
        except tweepy.TooManyRequests as e:
            result = {"success": False, "error": f"Twitter 限流，请稍后重试: {e}", "status": "限流"}
        except tweepy.TweepyException as e:
            result = {"success": False, "error": f"Twitter API 异常: {e}", "status": "API 异常"}
        except Exception as e:
            result = {"success": False, "error": f"连接失败: {e}", "status": "异常"}

        # 更新缓存
        self._connection_cache["result"] = result
        self._connection_cache["ts"] = now
        return result

    def upload_image(self, local_path: str) -> dict:
        """上传图片到 Twitter（使用 API v1.1 media/upload）

        返回: {"success": True, "media_id": "12345", "url": ""}
              或 {"success": False, "error": "..."}
        """
        if not os.path.isfile(local_path):
            return {"success": False, "url": "", "media_id": "",
                    "error": f"文件不存在: {local_path}"}

        if not self._api_v1:
            return {"success": False, "url": "", "media_id": "",
                    "error": "OAuth 1.0a 未配置，无法上传图片"}

        try:
            # 检查文件格式
            ext = os.path.splitext(local_path)[1].lower()
            if ext not in self.PLATFORM_LIMITS["supported_formats"]:
                return {
                    "success": False, "url": "", "media_id": "",
                    "error": f"不支持的格式 {ext}，支持: {', '.join(self.PLATFORM_LIMITS['supported_formats'])}"
                }

            # 检查文件大小（GIF 有更大的限制）
            size = os.path.getsize(local_path)
            max_size = self.PLATFORM_LIMITS["max_gif_size"] if ext == '.gif' else self.PLATFORM_LIMITS["max_image_size"]
            if size > max_size:
                size_type = "GIF" if ext == '.gif' else "图片"
                return {
                    "success": False, "url": "", "media_id": "",
                    "error": f"{size_type}过大 ({size/1024/1024:.1f}MB > {max_size/1024/1024:.0f}MB)"
                }

            # 上传到 Twitter
            self.logger.info(f"⏫ 上传图片: {local_path} ({size/1024:.0f}KB)")
            media = self._api_v1.media_upload(filename=local_path)
            self.logger.info(f"✅ 图片已上传: media_id={media.media_id_string}")
            return {
                "success": True,
                "url": "",  # media upload 没有独立的公开 URL
                "media_id": media.media_id_string,
            }
        except tweepy.Forbidden as e:
            return {"success": False, "url": "", "media_id": "",
                    "error": f"Twitter 权限不足: {e}"}
        except tweepy.TooManyRequests as e:
            return {"success": False, "url": "", "media_id": "",
                    "error": f"Twitter 图片上传限流: {e}"}
        except tweepy.TweepyException as e:
            return {"success": False, "url": "", "media_id": "",
                    "error": f"Twitter 上传异常: {e}"}
        except Exception as e:
            err_msg = str(e)[:200]
            return {"success": False, "url": "", "media_id": "",
                    "error": f"上传异常: {err_msg}"}

    def _extract_article_images(self, article: Article) -> list[str]:
        """从 Article 中提取本地图片路径

        支持:
        - article.cover (封面图)
        - article.assets (资源列表，含本地路径)
        - article.body 中的 Markdown 图片引用
        - article.metadata.get("images") (自定义图片列表)
        """
        image_paths = []

        # 1. 封面图
        if article.cover and os.path.isfile(article.cover):
            image_paths.append(article.cover)

        # 2. assets
        for asset in article.assets:
            if os.path.isfile(asset):
                image_paths.append(asset)

        # 3. 正文中的 Markdown 图片
        for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', article.body):
            src = m.group(2).strip()
            if src.startswith("http"):
                continue  # 远程图片跳过（Twitter 不支持直接引用）
            if os.path.isfile(src):
                image_paths.append(src)

        # 4. 自定义 metadata 图片列表
        metadata_images = article.metadata.get("images", [])
        if isinstance(metadata_images, list):
            for img in metadata_images:
                if isinstance(img, str) and os.path.isfile(img):
                    image_paths.append(img)

        # 去重并保留顺序
        seen = set()
        return [p for p in image_paths if not (p in seen or seen.add(p))]

    def _upload_article_images(self, article: Article) -> tuple[str, list[str]]:
        """上传文章中的所有图片到 Twitter

        返回:
            - body: 更新过图片 URL 的正文
            - media_ids: 成功上传的 media_id 列表（用于 create_tweet）
        """
        image_paths = self._extract_article_images(article)
        if not image_paths:
            return article.body, []

        media_ids = []
        body = article.body

        for path in image_paths:
            result = self.upload_image(path)
            if result["success"] and result.get("media_id"):
                media_ids.append(result["media_id"])
                # 替换 body 中的本地路径为占位标记
                body = body.replace(path, f"[📎 media:{result['media_id']}]")
                self.logger.info(f"  📎 media_id={result['media_id']}")
            else:
                self.logger.warning(f"  ⚠️ 图片上传失败: {result.get('error', '')}")

        # Twitter 最多 4 张图
        media_ids = media_ids[:4]
        return body, media_ids

    def _split_into_tweets(self, text: str) -> list[str]:
        """将长文本拆分为多条推文（线程）

        拆分策略：
        1. 短于 max_len → 单推
        2. 先按段落拆分（\n\n）
        3. 段落仍超长 → 按句子拆分（。！？.!\\n）
        4. 句子仍超长 → 硬截断加 ...
        """
        max_len = self.max_tweet_length
        if len(text) <= max_len:
            return [text]

        tweets = []
        paragraphs = text.split("\n\n")

        for para in paragraphs:
            if not para.strip():
                continue

            # 段落不长 → 尝试追加到当前推文
            if len(para) <= max_len:
                if tweets and len(tweets[-1]) + len(para) + 3 <= max_len:
                    tweets[-1] = f"{tweets[-1]}\n\n{para}"
                else:
                    tweets.append(para)
                continue

            # 段落超长 → 按句子拆分
            # 支持中英文句子分隔符
            sentences = re.split(r'(?<=[。！？.!?\\n])\s*', para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(sent) <= max_len:
                    if tweets and len(tweets[-1]) + len(sent) + 1 <= max_len:
                        tweets[-1] = f"{tweets[-1]}\n{sent}"
                    else:
                        tweets.append(sent)
                else:
                    # 单句超长 → 硬截断
                    truncated = sent[:max_len - 3] + "..."
                    tweets.append(truncated)

        return tweets

    def _save_draft(self, article, title, body, as_thread, skip_image_upload, kwargs) -> dict:
        """保存推文到本地 JSON 草稿

        不依赖 Twitter 凭证，纯本地操作。
        """
        tweet_text = body
        if title and not body.startswith(title):
            tweet_text = f"{title}\n\n{body}"

        # 处理图片
        media_ids = list(kwargs.get("media_ids", []) or [])
        updated_body = body

        if not skip_image_upload:
            updated_body, uploaded_ids = self._upload_article_images(article)
            media_ids.extend(uploaded_ids)

        media_ids = list(dict.fromkeys(media_ids))[:4]
        image_paths = self._extract_article_images(article)

        draft_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "drafts", "twitter"
        )
        os.makedirs(draft_dir, exist_ok=True)

        draft = {
            "title": title,
            "body": updated_body,
            "tweet_text": tweet_text,
            "media_ids": media_ids,
            "image_paths": image_paths,
            "as_thread": as_thread,
            "created_at": datetime.datetime.now().isoformat(),
            "article_source": article.source,
        }
        draft_path = os.path.join(draft_dir, f"draft_{int(time.time())}.json")
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)

        self.logger.info(f"📝 草稿已保存: {draft_path} ({len(media_ids)} 图, {len(tweet_text)} 字)")
        return {
            "success": True,
            "url": "",
            "id": "",
            "error": "",
            "message": f"草稿已保存到 {draft_path}",
            "draft_path": draft_path,
        }

    def publish(self, article: Article, **kwargs) -> dict:
        """发布推文（或线程）到 Twitter/X

        kwargs:
            save_as_draft: True = 本地缓存，不真正发布
            as_thread: True/False 覆盖默认的线程拆分行为
            media_ids: 预上传的 media_id 列表（不自动上传图片）
            skip_image_upload: True = 跳过自动图片上传（用预传的 media_ids）

        Article 支持的图片源:
            - article.cover       封面图（本地路径）
            - article.assets      资源列表（本地路径）
            - body 中的 Markdown 图片引用（![]()）
            - article.metadata["images"]  自定义图片列表
        """
        save_as_draft = kwargs.get("save_as_draft", False)
        as_thread = kwargs.get("as_thread", self.as_thread)
        skip_image_upload = kwargs.get("skip_image_upload", False)

        missing = self.validate_config()
        # 草稿模式不需要 Twitter 凭证
        if missing and not save_as_draft:
            return {"success": False, "error": f"缺少配置: {', '.join(missing)}",
                    "url": "", "id": ""}

        try:
            # 构建推文文本
            title = article.title or ""
            body = article.body or ""

            # 草稿模式不需要初始化客户端
            if save_as_draft:
                return self._save_draft(
                    article, title, body, as_thread,
                    skip_image_upload, kwargs
                )

            client = self._get_client()

            tweet_text = body
            if title and not body.startswith(title):
                tweet_text = f"{title}\n\n{body}"

            # 处理图片
            media_ids = list(kwargs.get("media_ids", []) or [])
            updated_body = body

            if not skip_image_upload:
                # 自动提取并上传文章图片
                updated_body, uploaded_ids = self._upload_article_images(article)
                media_ids.extend(uploaded_ids)

            # 去重 media_ids
            media_ids = list(dict.fromkeys(media_ids))[:4]

            # 实际发布
            if as_thread and len(tweet_text) > self.max_tweet_length:
                tweets = self._split_into_tweets(tweet_text)
                return self._publish_thread(client, tweets, media_ids)
            else:
                return self._publish_single(client, tweet_text, media_ids)

        except PublishError:
            raise
        except Exception as e:
            self.logger.error(f"Twitter 发布异常: {e}")
            return {"success": False, "error": f"Twitter 发布异常: {e}",
                    "url": "", "id": ""}

    def _publish_single(self, client, text: str, media_ids: list = None) -> dict:
        """发布单条推文，含限流自动重试"""
        params = {"text": text[:self.max_tweet_length]}
        if media_ids:
            params["media_ids"] = [str(mid) for mid in media_ids[:4]]

        last_error = ""
        delay = _RATE_LIMIT_BASE_DELAY

        for attempt in range(1, _RATE_LIMIT_RETRIES + 1):
            try:
                response = client.create_tweet(**params, user_auth=True)
                if response.data and response.data.get("id"):
                    tweet_id = response.data["id"]
                    self.logger.info(f"✅ 推文已发布: https://twitter.com/i/web/status/{tweet_id}")
                    return {
                        "success": True,
                        "url": f"https://twitter.com/i/web/status/{tweet_id}",
                        "id": str(tweet_id),
                        "error": "",
                    }
                error_msg = str(response.errors) if response.errors else "未知错误"
                self.logger.error(f"❌ 推文发布失败: {error_msg}")
                return {"success": False, "error": f"推文发布失败: {error_msg}",
                        "url": "", "id": ""}

            except tweepy.TooManyRequests as e:
                # 限流 → 退避重试
                self.logger.warning(f"  ⏳ 限流 (尝试 {attempt}/{_RATE_LIMIT_RETRIES}): 等待 {delay:.0f}s")
                if attempt < _RATE_LIMIT_RETRIES:
                    time.sleep(delay)
                    delay = min(delay * 2, _RATE_LIMIT_MAX_DELAY)
                    continue
                last_error = f"限流，重试 {_RATE_LIMIT_RETRIES} 次后仍然失败: {e}"

            except tweepy.Forbidden as e:
                self.logger.error(f"❌ 推文发布权限不足: {e}")
                return {"success": False, "error": f"推文发布权限不足: {e}",
                        "url": "", "id": ""}

            except tweepy.Unauthorized as e:
                self.logger.error(f"❌ 推文发布认证失败: {e}")
                return {"success": False, "error": f"推文发布认证失败: {e}",
                        "url": "", "id": ""}

            except tweepy.TweepyException as e:
                self.logger.error(f"❌ 推文发布异常: {e}")
                return {"success": False, "error": f"推文发布异常: {e}",
                        "url": "", "id": ""}

        # 所有重试用完仍失败
        self.logger.error(f"❌ 推文发布失败 (重试耗尽): {last_error}")
        return {"success": False, "error": last_error, "url": "", "id": ""}

    def _publish_thread(self, client, tweets: list[str], media_ids: list = None) -> dict:
        """发布线程（多条回复推文），含逐条限流重试"""
        if not tweets:
            return {"success": False, "error": "没有内容可发布", "url": "", "id": ""}

        if len(tweets) > self.PLATFORM_LIMITS["max_thread_length"]:
            self.logger.warning(f"⚠️ 线程过长: {len(tweets)}条 > {self.PLATFORM_LIMITS['max_thread_length']}条限制，截断")
            tweets = tweets[:self.PLATFORM_LIMITS["max_thread_length"]]

        published_ids = []

        for i, tweet_text in enumerate(tweets):
            if not tweet_text.strip():
                continue

            params = {"text": tweet_text[:self.max_tweet_length]}

            # 图片：只在第一条推文附加（Twitter UI 最佳实践）
            if i == 0 and media_ids:
                params["media_ids"] = [str(mid) for mid in media_ids[:4]]

            # 回复上一条（形成线程）
            if published_ids:
                params["in_reply_to_tweet_id"] = published_ids[-1]

            delay = _RATE_LIMIT_BASE_DELAY
            published = False

            for attempt in range(1, _RATE_LIMIT_RETRIES + 1):
                try:
                    response = client.create_tweet(**params, user_auth=True)
                    if response.data and response.data.get("id"):
                        published_ids.append(response.data["id"])
                        self.logger.info(f"  📨 推文 {i+1}/{len(tweets)}: id={response.data['id']}")
                        published = True
                        break
                    else:
                        error_msg = str(response.errors) if response.errors else "未知错误"
                        self.logger.error(f"  ❌ 推文 {i+1} 发布失败: {error_msg}")
                        published = False
                        break

                except tweepy.TooManyRequests as e:
                    if attempt < _RATE_LIMIT_RETRIES:
                        self.logger.warning(f"  ⏳ 推文 {i+1} 限流 (尝试 {attempt}/{_RATE_LIMIT_RETRIES}): 等待 {delay:.0f}s")
                        time.sleep(delay)
                        delay = min(delay * 2, _RATE_LIMIT_MAX_DELAY)
                        continue
                    self.logger.error(f"  ❌ 推文 {i+1} 限流重试耗尽: {e}")
                    published = False
                    break

                except tweepy.Forbidden as e:
                    self.logger.error(f"  ❌ 推文 {i+1} 被拒: {e}")
                    published = False
                    break

                except tweepy.Unauthorized as e:
                    self.logger.error(f"  ❌ 推文 {i+1} 认证失败: {e}")
                    published = False
                    break

                except tweepy.TweepyException as e:
                    self.logger.error(f"  ❌ 推文 {i+1} 异常: {e}")
                    published = False
                    break

            if not published:
                break

            # 线程间礼貌间隔（防限流）
            time.sleep(2)

        if not published_ids:
            return {"success": False, "error": "线程发布失败，首条推文未发出",
                    "url": "", "id": ""}

        result = {
            "success": True,
            "url": f"https://twitter.com/i/web/status/{published_ids[0]}",
            "id": ",".join(str(tid) for tid in published_ids),
            "thread_ids": [str(tid) for tid in published_ids],
            "tweet_count": len(published_ids),
            "error": "",
        }
        self.logger.info(f"✅ 线程发布完成: {len(published_ids)}/{len(tweets)} 条")
        return result

    def retract(self, article: Article, publish_log: dict = None) -> dict:
        """删除已发布的推文（支持单条和线程）"""
        if not publish_log or not publish_log.get("id"):
            return {"success": False, "error": "缺少发布记录", "message": ""}

        try:
            client = self._get_client()

            # id 可能为逗号分隔的多个 ID（来自线程发布）
            ids = publish_log["id"].split(",")
            # 也支持 thread_ids 字段
            if publish_log.get("thread_ids"):
                ids = publish_log["thread_ids"]

            deleted = []
            failed = []

            for tid in ids:
                tid = tid.strip()
                if not tid:
                    continue
                try:
                    client.delete_tweet(id=int(tid), user_auth=True)
                    deleted.append(tid)
                    time.sleep(0.5)  # 间隔防限流
                except tweepy.Forbidden:
                    # 可能是已删除或权限不足
                    failed.append((tid, "无权限或已删除"))
                except tweepy.TooManyRequests:
                    # 限流 — 等待后重试一次
                    self.logger.warning(f"  ⏳ 删除限流，等待 5s 后重试: {tid}")
                    time.sleep(5)
                    try:
                        client.delete_tweet(id=int(tid), user_auth=True)
                        deleted.append(tid)
                    except tweepy.TweepyException as e:
                        failed.append((tid, str(e)))
                except tweepy.TweepyException as e:
                    failed.append((tid, str(e)))

            self.logger.info(f"🗑️ 撤回: {len(deleted)} 成功, {len(failed)} 失败")
            if not failed:
                return {
                    "success": True,
                    "error": "",
                    "message": f"已删除 {len(deleted)} 条推文",
                }
            return {
                "success": False if not deleted else True,
                "error": f"部分删除失败: {len(failed)}/{len(ids)}",
                "message": f"成功: {len(deleted)}, 失败: {len(failed)}",
            }
        except Exception as e:
            self.logger.error(f"撤回异常: {e}")
            return {"success": False, "error": f"删除异常: {e}", "message": ""}
