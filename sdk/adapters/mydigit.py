"""
mydigit.cn (数码之家) 平台适配器

基于 Discuz! 引擎，包装现有 FlashSloth 插件提供统一接口。

支持的接口:
  - sign_in()         k_misign 签到
  - publish()         发布帖子
  - fetch_posts()     采集新帖
  - fetch_replies()   采集回复
  - fetch_thread_detail() 读帖详情
  - browse_forum()    逛论坛
"""
import re
import time
from typing import Optional

from ..adapter import PlatformAdapter, register, alias, Article, Comment, get_db
from plugins.publisher_discuz import DiscuzPublisher
from plugins.forum_reader import DiscuzForumReader


@register
@alias('discuz')
class MydigitAdapter(PlatformAdapter):
    name = "mydigit"
    display_name = "数码之家"
    site_url = "https://www.mydigit.cn"
    version = "1.0.0"
    description = "数码之家 (mydigit.cn) — 基于 Discuz! 引擎的数码/硬件技术社区"
    icon = "🔧"

    config_fields = [
        {
            "key": "site_url",
            "label": "论坛地址",
            "type": "text",
            "required": True,
            "placeholder": "https://www.mydigit.cn",
        },
        {
            "key": "cookie",
            "label": "Cookie",
            "type": "password",
            "required": True,
            "placeholder": "登录后从浏览器 F12 复制 Cookie",
        },
        {
            "key": "username",
            "label": "用户名",
            "type": "text",
            "required": False,
            "placeholder": "论坛登录用户名（可选，用于验证登录状态）",
        },
        {
            "key": "password",
            "label": "密码",
            "type": "password",
            "required": False,
            "placeholder": "论坛登录密码（可选，密码模式需额外验证码）",
        },
        {
            "key": "fid",
            "label": "板块 ID",
            "type": "text",
            "required": False,
            "placeholder": "默认发布板块的 fid（如 2）",
        },
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        cfg = config or {}
        self.site_url = cfg.get("site_url", "https://www.mydigit.cn").rstrip("/")
        self.cookie = cfg.get("cookie", "")
        self.username = cfg.get("username", "")
        self.password = cfg.get("password", "")
        self.fid = cfg.get("fid", "")

    # ─── 内部工具 ─────────────────────────────────

    def _make_reader(self) -> DiscuzForumReader:
        """创建已登录的论坛读取器"""
        return DiscuzForumReader(
            site_url=self.site_url,
            cookies=self.cookie,
            username=self.username,
            password=self.password,
        )

    def _make_publisher(self) -> DiscuzPublisher:
        """创建 Discuz 发布器"""
        return DiscuzPublisher({
            "site_url": self.site_url,
            "cookie": self.cookie,
            "username": self.username,
            "password": self.password,
            "fid": self.fid,
            "login_mode": "cookie",
        })

    def validate_config(self) -> list[str]:
        """检查配置完整性"""
        missing = []
        if not self.site_url:
            missing.append("论坛地址")
        if not self.cookie:
            missing.append("Cookie")
        return missing

    # ─── 签到 ─────────────────────────────────────

    def sign_in(self, check_only: bool = False) -> dict:
        """
        使用 k_misign 插件签到。
        模拟 DiscuzKmisignSignin 的签到流程。
        """
        if check_only:
            return {"supported": True, "message": "支持 k_misign 签到"}

        missing = self.validate_config()
        if missing:
            return {
                "supported": True,
                "success": False,
                "already_signed": False,
                "error": f"缺少配置: {', '.join(missing)}",
                "message": "",
            }

        try:
            from plugins.browser_session import HumanSession

            browser = HumanSession(
                base_url=self.site_url, min_delay=0.5, max_delay=2.0
            )
            browser.set_cookies(self.cookie)

            sign_url = self.site_url.rstrip("/") + "/k_misign-sign.html"
            resp = browser.get(sign_url)

            # 检查登录状态
            uid_match = re.search(r"discuz_uid\s*=\s*'(\d+)'", resp.text)
            if not uid_match or uid_match.group(1) == "0":
                return {
                    "supported": True,
                    "success": False,
                    "already_signed": False,
                    "error": "Cookie 无效，未登录",
                    "message": "",
                }

            # 检查是否已签到
            status_indicators = [
                "已签", "已签到", "签到成功", "今日已签", "您的签到排名",
            ]
            if any(t in resp.text for t in status_indicators):
                return {
                    "supported": True,
                    "success": True,
                    "already_signed": True,
                    "error": "",
                    "message": "今天已签到",
                }

            # 提取 formhash
            formhash = None
            for pattern in [
                r'name="formhash"[^>]+value="([^"]+)"',
                r'formhash\s*=\s*"([^"]+)"',
                r'formhash=([a-zA-Z0-9]+)',
            ]:
                match = re.search(pattern, resp.text)
                if match:
                    formhash = match.group(1)
                    break

            if not formhash:
                link_match = re.search(
                    r'k_misign:sign&operation=qiandao&formhash=([a-zA-Z0-9]+)',
                    resp.text,
                )
                if link_match:
                    formhash = link_match.group(1)

            if not formhash:
                return {
                    "supported": True,
                    "success": False,
                    "already_signed": False,
                    "error": "无法获取 formhash",
                    "message": "",
                }

            # 执行签到
            qiandao_url = (
                f"{self.site_url}/plugin.php?id=k_misign:sign"
                f"&operation=qiandao&formhash={formhash}&format=empty"
            )
            browser.get(qiandao_url)
            time.sleep(1)

            # 验证签到结果
            verify_resp = browser.get(sign_url)
            if any(t in verify_resp.text for t in status_indicators):
                return {
                    "supported": True,
                    "success": True,
                    "already_signed": False,
                    "error": "",
                    "message": "签到成功 ✅",
                }

            return {
                "supported": True,
                "success": False,
                "already_signed": False,
                "error": "签到失败，未知原因",
                "message": "",
            }

        except Exception as e:
            return {
                "supported": True,
                "success": False,
                "already_signed": False,
                "error": f"签到异常: {e}",
                "message": "",
            }

    # ─── 发布 ─────────────────────────────────────

    def publish(self, article: Article, **kwargs) -> dict:
        """
        发布帖子到 mydigit.cn。
        委托给 DiscuzPublisher。
        """
        try:
            publisher = self._make_publisher()
            # 优先使用 kwargs 中的 fid，否则使用配置中的 fid
            pub_kwargs = {}
            fid = kwargs.get("fid", self.fid)
            if fid:
                pub_kwargs["fid"] = fid
            result = publisher.publish(article, **pub_kwargs)
            return result
        except Exception as e:
            return {
                "supported": True,
                "success": False,
                "url": "",
                "id": "",
                "error": f"发布异常: {e}",
                "message": "",
            }

    # ─── 采集帖子 ─────────────────────────────────

    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """
        采集指定板块的新帖子。
        使用 DiscuzForumReader.get_new_threads() 获取原始数据，
        转换为 Article 列表返回。
        """
        fid = kwargs.get("fid", self.fid)
        if not fid:
            return []

        try:
            reader = self._make_reader()
            raw_threads = reader.get_new_threads(
                fid=fid, hours=hours, max_pages=max_pages
            )

            articles = []
            for t in raw_threads:
                article = Article(
                    title=t.get("title", ""),
                    source="mydigit",
                    source_url=t.get("url", ""),
                    source_id=t.get("tid", ""),
                    summary="",
                    body="",
                    tags=[],
                    author="",
                    raw=t,
                )
                articles.append(article)
            return articles

        except Exception as e:
            return []

    # ─── 采集回复 ─────────────────────────────────

    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """
        采集指定帖子的回复。
        使用 DiscuzForumReader.get_replies_to_my_threads()。
        """
        if not thread_ids:
            return []

        try:
            reader = self._make_reader()
            raw_replies = reader.get_replies_to_my_threads(
                my_thread_tids=thread_ids,
                max_pages=kwargs.get("max_pages", 2),
            )

            comments = []
            for r in raw_replies:
                comment = Comment(
                    id="",
                    author=r.get("author", ""),
                    content=r.get("content", ""),
                    created_at=None,
                    parent_id="",
                    thread_id=r.get("thread_tid", ""),
                )
                comments.append(comment)
            return comments

        except Exception as e:
            return []

    # ─── 读帖详情 ─────────────────────────────────

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """
        获取单篇帖子的详细内容。
        使用 DiscuzForumReader.get_thread_detail()。
        """
        if not thread_id:
            return None

        try:
            reader = self._make_reader()
            detail = reader.get_thread_detail(tid=thread_id)
            if not detail:
                return None

            return Article(
                title="",
                body=detail.get("content", ""),
                summary="",
                tags=[],
                source="mydigit",
                source_url=(
                    f"{self.site_url}/forum.php?mod=viewthread&tid={thread_id}"
                ),
                source_id=thread_id,
                author=detail.get("author", ""),
                raw=detail,
            )

        except Exception as e:
            return None

    # ─── 逛论坛 ───────────────────────────────────

    def browse_forum(self, **kwargs) -> dict:
        """
        浏览论坛板块列表，推荐感兴趣的内容。
        使用 DiscuzForumReader.get_forum_list() 获取板块列表。
        """
        try:
            reader = self._make_reader()
            forums = reader.get_forum_list()

            result = {
                "supported": True,
                "total": len(forums),
                "filtered": 0,
                "new_saved": 0,
                "forums": forums,
            }

            # 如果指定了 fid，进一步获取该板块的新帖
            fid = kwargs.get("fid", self.fid)
            if fid:
                hours = kwargs.get("hours", 24)
                max_pages = kwargs.get("max_pages", 1)
                threads = reader.get_new_threads(
                    fid=fid, hours=hours, max_pages=max_pages
                )
                result["threads"] = threads
                result["filtered"] = len(threads)

            return result

        except Exception as e:
            return {
                "supported": True,
                "total": 0,
                "filtered": 0,
                "new_saved": 0,
                "forums": [],
                "error": str(e),
            }

    # ─── 测试连接 ─────────────────────────────────

    def test_connection(self) -> dict:
        """测试账号配置是否可用"""
        try:
            reader = self._make_reader()
            logged_in = reader.is_logged_in()
            if logged_in:
                return {
                    "supported": True,
                    "success": True,
                    "error": "",
                    "status": "已登录",
                }
            return {
                "supported": True,
                "success": False,
                "error": "Cookie 无效或已过期",
                "status": "未登录",
            }
        except Exception as e:
            return {
                "supported": True,
                "success": False,
                "error": f"连接失败: {e}",
                "status": "连接失败",
            }
