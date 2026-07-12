"""
闲鱼 (Xianyu / goofish.com) 平台适配器

基于 Playwright 浏览器自动化 + Cookie 方式访问闲鱼平台。

能力清单：
  - sign_in()            每日签到（不支持，闲鱼无签到功能）
  - publish()            发布商品（框架预留，实际发布需对接闲鱼开放平台 API）
  - retract()            下架商品（框架预留）
  - fetch_posts()        采集商品列表（Playwright 浏览器搜索 ✅）
  - fetch_replies()      采集留言/评论（不支持）
  - fetch_thread_detail() 获取商品详情（Playwright 浏览器 ✅）
  - reply_comment()      回复买家留言（不支持）
  - browse_forum()       逛闲鱼（Playwright 浏览器 ✅）
  - deploy()             部署（不支持）

登录方式：
  1. Cookie 模式：用户通过 Playwright 登录后获取 Cookie 保存
  2. Playwright 浏览器自动登录：填写淘宝账号密码 + 处理验证码/扫码
"""
from typing import Optional
import json

from ..adapter import PlatformAdapter, register, Article, Comment


@register
class XianyuAdapter(PlatformAdapter):
    name = "xianyu"
    display_name = "闲鱼"
    site_url = "https://goofish.com"
    version = "1.0.0"
    description = "闲鱼二手交易平台 — 阿里巴巴旗下 (goofish.com)"
    icon = "🐟"

    config_fields = [
        {
            "key": "login_mode",
            "label": "登录方式",
            "type": "select",
            "required": True,
            "options": [
                {"value": "cookie", "label": "Cookie 方式（从浏览器复制）"},
                {"value": "playwright", "label": "浏览器自动登录（需账号密码）"},
            ],
            "placeholder": "选择登录方式",
        },
        {
            "key": "taobao_account",
            "label": "淘宝账号（手机号/邮箱）",
            "type": "text",
            "required": False,
            "placeholder": "登录闲鱼的淘宝账号",
        },
        {
            "key": "password",
            "label": "淘宝密码",
            "type": "password",
            "required": False,
            "placeholder": "淘宝账号登录密码",
        },
        {
            "key": "cookie",
            "label": "Cookie（Cookie模式）",
            "type": "password",
            "required": False,
            "placeholder": "登录后从浏览器 F12 复制 Cookie",
        },
    ]

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.login_mode = config.get("login_mode", "cookie") if config else "cookie"
        self.taobao_account = config.get("taobao_account", "") if config else ""
        self.password = config.get("password", "") if config else ""
        self.cookie = config.get("cookie", "") if config else ""
        self.site_url = "https://goofish.com"
        self._login_instance = None

    # ─── 签到 ─────────────────────────────────

    def sign_in(self, check_only: bool = False) -> dict:
        """闲鱼无签到功能"""
        return {"supported": False}

    # ─── 发布 ─────────────────────────────────

    def publish(self, article: Article, **kwargs) -> dict:
        """发布商品到闲鱼

        将 Article 数据转为闲鱼商品发布。

        Article 字段映射:
            title        → 商品标题
            body         → 商品描述
            images       → 商品图片
            summary      → 卖点/摘要

        kwargs 支持:
            price (str)         — 价格（必填）
            condition (str)     — 成色: new/like_new/slight_use/obvious_use/damaged
            category (str)      — 分类 ID
            delivery (str)      — 发货方式: express/in_person/virtual
            quantity (int)      — 库存（默认1）
            original_price (str)— 原价
            location (str)      — 所在地
            contact (str)       — 联系方式

        当前以登录 + Cookie 管理为主，实际对接需闲鱼开放平台。
        """
        missing = self.validate_config()
        if missing:
            return {
                "success": False, "url": "", "id": "",
                "error": f"缺少配置: {', '.join(missing)}",
            }

        if self.login_mode == "playwright":
            return {
                "success": False, "url": "", "id": "",
                "error": "请先完成浏览器登录后再发布商品",
            }

        if not self._has_valid_cookie():
            return {
                "success": False, "url": "", "id": "",
                "error": "Cookie 无效或已过期，请重新登录",
            }

        title = article.title.strip()
        if not title:
            return {"success": False, "url": "", "id": "", "error": "商品标题不能为空"}

        price = kwargs.get("price", self.config.get("default_price", ""))
        if not price:
            return {
                "success": False, "url": "", "id": "",
                "error": "商品价格不能为空，请传入 price 参数或在配置中设置默认价格",
            }

        product_data = {
            "title": title[:30],
            "description": (article.body or "")[:500],
            "price": str(price),
            "condition": kwargs.get("condition", self.config.get("default_condition", "slight_use")),
            "category": kwargs.get("category", self.config.get("default_category", "")),
            "delivery": kwargs.get("delivery", self.config.get("default_delivery", "express")),
            "quantity": kwargs.get("quantity", 1),
            "original_price": kwargs.get("original_price", ""),
            "location": kwargs.get("location", ""),
            "contact": kwargs.get("contact", ""),
            "images": kwargs.get("images", article.images or []),
            "summary": article.summary or "",
            "tags": article.tags or [],
        }

        # 预留 — 对接开放平台 API 或 Playwright 模拟
        return {
            "success": False, "url": "", "id": "",
            "error": "闲鱼商品发布需对接闲鱼开放平台 API，当前版本尚未实现完整发布流程",
            "message": json.dumps(product_data, ensure_ascii=False),
        }

    def _has_valid_cookie(self) -> bool:
        """检查 Cookie 是否有效（包含闲鱼/淘宝关键认证字段）"""
        if not self.cookie:
            return False
        required_keys = [
            "_tb_token_", "cookie2", "t", "sid",
            "alimamapwg", "munb", "ucn", "lgc",
        ]
        found = sum(1 for k in required_keys if k in self.cookie)
        return found >= 2

    # ─── 撤回/下架 ─────────────────────────────

    def retract(self, article_id: str, publish_log: dict = None) -> dict:
        """下架商品（框架预留）"""
        return {"supported": False}

    # ─── 采集 ─────────────────────────────────

    def fetch_replies(self, thread_ids: list[str] = None, **kwargs) -> list[Comment]:
        """闲鱼留言暂不支持自动采集"""
        return []

    # ─── 互动 ─────────────────────────────────

    def reply_comment(self, thread_id: str, content: str, comment_id: str = None) -> dict:
        """回复留言（暂不支持）"""
        return {"supported": False}

    # ─── 逛闲鱼 ───────────────────────────────

    def browse_forum(self, **kwargs) -> dict:
        """
        浏览闲鱼首页 / 搜索商品。

        需要已登录的 Cookie（Playwright 模式或 Cookie 模式）。
        通过 Playwright 打开 goofish.com 提取商品信息。
        """
        query = kwargs.get("q", "")
        if not query:
            query = kwargs.get("keyword", "")

        # 尝试 Playwright 浏览器模式
        try:
            from plugins.xianyu_login import XianyuPlaywrightLogin
            login = XianyuPlaywrightLogin()

            # 如果已有 cookie，注入后直接浏览
            if self.cookie:
                login.cookie = self.cookie
                login._ensure_browser()
                # 访问 goofish 搜索页
                search_url = f"https://goofish.com/search?q={query}" if query else "https://goofish.com"
                login.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                import time
                time.sleep(3)

                # 提取商品列表
                items = []
                try:
                    # 尝试提取商品卡片
                    cards = login.page.query_selector_all("[class*='item'], [class*='card'], [class*='product']")
                    for card in cards[:30]:
                        try:
                            title_el = card.query_selector("a, [class*='title'], [class*='name']")
                            price_el = card.query_selector("[class*='price']")
                            title = title_el.inner_text().strip() if title_el else ""
                            price = price_el.inner_text().strip() if price_el else ""
                            if title:
                                items.append({"title": title, "price": price})
                        except:
                            continue
                except:
                    pass

                login.close()
                return {"supported": True, "total": len(items), "items": items[:20],
                        "message": "需要登录闲鱼后才能浏览商品详情" if not items else ""}

            return {"supported": True, "total": 0, "items": [],
                    "error": "需要先登录闲鱼（Cookie 模式或 Playwright 模式）"}
        except ImportError:
            return {"supported": True, "total": 0, "items": [],
                    "error": "缺少 Playwright，请安装: pip install playwright"}
        except Exception as e:
            return {"supported": True, "total": 0, "items": [],
                    "error": f"浏览异常: {e}"}

    def fetch_posts(self, hours: int = 24, max_pages: int = 3, **kwargs) -> list[Article]:
        """
        搜索闲鱼商品列表，返回 Article 列表。

        需要已登录的 Cookie + Playwright 浏览器。
        搜索关键词通过 kwargs['q'] 或 kwargs['keyword'] 传入。
        """
        query = kwargs.get("q") or kwargs.get("keyword") or ""
        if not query:
            return []

        if not self.cookie:
            return []

        try:
            from plugins.xianyu_login import XianyuPlaywrightLogin
            login = XianyuPlaywrightLogin()
            if self.cookie:
                login.cookie = self.cookie
            login._ensure_browser()

            search_url = f"https://goofish.com/search?q={query}"
            login.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            import time
            time.sleep(3)

            articles = []
            cards = login.page.query_selector_all("[class*='item'], [class*='card'], [class*='product']")
            for card in cards[:30]:
                try:
                    title_el = card.query_selector("a, [class*='title'], [class*='name']")
                    price_el = card.query_selector("[class*='price']")
                    link_el = card.query_selector("a[href]")
                    title = title_el.inner_text().strip() if title_el else ""
                    price = price_el.inner_text().strip() if price_el else ""
                    href = link_el.get_attribute("href") if link_el else ""
                    if title:
                        articles.append(Article(
                            title=title,
                            source="xianyu",
                            source_url=f"https://goofish.com{href}" if href and href.startswith("/") else href,
                            body=f"价格: {price}" if price else "",
                            summary=price,
                            raw={"price": price},
                        ))
                except:
                    continue

            login.close()
            return articles
        except Exception:
            return []

    def fetch_thread_detail(self, thread_id: str) -> Optional[Article]:
        """
        获取闲鱼商品详情（需要已登录）。
        thread_id 是商品 ID 或完整 URL。
        """
        if not thread_id or not self.cookie:
            return None

        # 支持传入完整 URL 或商品 ID
        if thread_id.startswith("http"):
            item_url = thread_id
        else:
            item_url = f"https://goofish.com/item/{thread_id}"

        try:
            from plugins.xianyu_login import XianyuPlaywrightLogin
            login = XianyuPlaywrightLogin()
            if self.cookie:
                login.cookie = self.cookie
            login._ensure_browser()
            login.page.goto(item_url, wait_until="domcontentloaded", timeout=30000)
            import time
            time.sleep(3)

            # 提取标题
            title = ""
            for sel in ["[class*='title'] h1", "h1", "[class*='name']"]:
                try:
                    el = login.page.query_selector(sel)
                    if el:
                        title = el.inner_text().strip()
                        if title:
                            break
                except:
                    continue

            # 提取价格
            price = ""
            for sel in ["[class*='price']", "[class*='Price']"]:
                try:
                    el = login.page.query_selector(sel)
                    if el:
                        price = el.inner_text().strip()
                        break
                except:
                    continue

            # 提取描述
            desc = ""
            for sel in ["[class*='desc']", "[class*='Desc']", "[class*='detail']", "[class*='content']"]:
                try:
                    el = login.page.query_selector(sel)
                    if el:
                        desc = el.inner_text().strip()[:500]
                        break
                except:
                    continue

            login.close()

            body_parts = []
            if price:
                body_parts.append(f"价格: {price}")
            if desc:
                body_parts.append(f"\n{desc}")

            return Article(
                title=title or f"闲鱼商品 {thread_id}",
                body="\n".join(body_parts),
                source="xianyu",
                source_url=item_url,
                source_id=thread_id,
                summary=price,
            )
        except Exception:
            return None

    # ─── 部署 ─────────────────────────────────

    def deploy(self, check_only: bool = False, **kwargs) -> dict:
        """闲鱼不涉及站点部署"""
        return {"supported": False}

    # ─── 登录管理 ─────────────────────────────

    def test_connection(self) -> dict:
        """测试连接 — 检查 Cookie 有效性或提示需要登录"""
        if self.login_mode == "cookie":
            return self._test_cookie()
        else:
            return {
                "success": False,
                "error": "Playwright 模式需先验证验证码才能测试连接",
                "needs_captcha": True,
            }

    def _test_cookie(self) -> dict:
        """测试 Cookie 有效性 — 访问 goofish.com 检查"""
        if not self.cookie:
            return {
                "success": False, "error": "Cookie 为空", "status": "无 Cookie",
            }
        if not self._has_valid_cookie():
            return {
                "success": False, "error": "Cookie 缺少必要字段",
                "status": "Cookie 格式错误",
            }
        try:
            import requests
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Cookie": self.cookie,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            resp = requests.get(
                self.site_url, headers=headers, timeout=10,
                allow_redirects=True,
            )
            # 如果返回了用户信息页面，说明 Cookie 有效
            text = resp.text
            if "goofish" in resp.url.lower() and resp.status_code == 200:
                # 检查是否包含用户信息标记
                user_indicators = [
                    "my", "user", "个人", "我的",
                    "logout", "退出",
                ]
                has_user_info = any(ind in text.lower() for ind in user_indicators)
                # 检查是否跳回登录页
                if has_user_info:
                    return {
                        "success": True, "error": "", "status": "已登录",
                    }
                return {
                    "success": True, "error": "",
                    "status": "Cookie 有效，但无法确认登录身份",
                }
            if "login" in resp.url.lower():
                return {
                    "success": False, "error": "Cookie 已过期",
                    "status": "Cookie 过期",
                }
            return {
                "success": False, "error": f"返回状态码: {resp.status_code}",
                "status": "连接失败",
            }
        except Exception as e:
            return {
                "success": False, "error": f"连接异常: {e}",
                "status": "连接失败",
            }

    # ─── 商品搜索 ─────────────────────────────
    # 基于 XianyuAutoAgent API v2 (xianyu_v2.py)

    def search_products(
        self,
        keyword: str,
        min_price: float = 0,
        max_price: float = 0,
        sort_by: str = "default",
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """搜索闲鱼商品

        参数:
            keyword:     搜索关键词
            min_price:    最低价(0=不限)
            max_price:    最高价(0=不限)
            sort_by:     default | price_asc | price_desc | time
            page:         页码
            page_size:    每页数量

        返回:
            supported: bool
            success: bool
            total: int
            products: list[dict]
            error: str
        """
        try:
            from .xianyu_v2 import XianyuApiV2

            cookie = self.config.get("cookie", "") if self.config else ""
            if not cookie:
                return {"supported": True, "success": False,
                        "error": "未配置闲鱼Cookie，请在账号设置中添加"}

            client = XianyuApiV2(cookie)
            results = client.search_products(
                keyword=keyword, min_price=min_price, max_price=max_price,
                sort_by=sort_by, page=page, page_size=page_size,
            )
            return {
                "supported": True,
                "success": True,
                "total": len(results),
                "products": [p.__dict__ for p in results],
            }
        except Exception as e:
            return {"supported": True, "success": False,
                    "error": f"搜索失败: {e}"}

    def get_product_detail(self, item_id: str) -> dict:
        """获取商品详情

        返回:
            supported: bool
            success: bool
            product: dict | None
            error: str
        """
        try:
            from .xianyu_v2 import XianyuApiV2

            cookie = self.config.get("cookie", "") if self.config else ""
            if not cookie:
                return {"supported": True, "success": False,
                        "error": "未配置闲鱼Cookie"}

            client = XianyuApiV2(cookie)
            product = client.get_item_info(item_id)
            if product:
                return {"supported": True, "success": True,
                        "product": product.__dict__}
            return {"supported": True, "success": False,
                    "error": "商品不存在或无法访问"}
        except Exception as e:
            return {"supported": True, "success": False,
                    "error": f"获取详情失败: {e}"}

    # ─── Playwright 登录 ──────────────────────

    def playwright_login(self) -> dict:
        """使用 Playwright 浏览器自动登录闲鱼

        返回:
            success: bool
            logged_in: bool
            needs_captcha: bool
            image: str (base64 screenshot)
            captcha_type: str
            cookie: str (登录成功时)
            error: str
        """
        try:
            from plugins.xianyu_login import XianyuPlaywrightLogin

            if not self.taobao_account or not self.password:
                return {
                    "success": False, "logged_in": False,
                    "error": "请在配置中填写淘宝账号和密码",
                }

            login = XianyuPlaywrightLogin()
            self._login_instance = login
            result = login.login(
                taobao_account=self.taobao_account,
                password=self.password,
            )

            if result.get("logged_in"):
                # 保存 Cookie
                self.cookie = result.get("cookies", "")
                if self.config is not None:
                    self.config["cookie"] = self.cookie

            return result

        except ImportError as e:
            return {
                "success": False, "logged_in": False,
                "error": f"缺少依赖: {e}，请先安装 Playwright",
            }
        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"Playwright 登录异常: {e}",
            }

    def check_playwright_login_status(self) -> dict:
        """检查 Playwright 登录状态（用户处理验证码/扫码后调用）"""
        try:
            from plugins.xianyu_login import XianyuPlaywrightLogin

            login = self._login_instance or XianyuPlaywrightLogin()
            self._login_instance = login
            result = login.check_login_status()

            if result.get("logged_in"):
                self.cookie = result.get("cookies", "")
                if self.config is not None:
                    self.config["cookie"] = self.cookie

            return result

        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"检查登录状态异常: {e}",
            }

    def close_browser(self):
        """关闭 Playwright 浏览器实例"""
        if self._login_instance:
            try:
                self._login_instance.close()
            except Exception:
                pass
            self._login_instance = None

    def __del__(self):
        self.close_browser()
