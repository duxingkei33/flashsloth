"""
闲鱼 (Xianyu / goofish.com) 商品 Publisher — 发布二手商品到闲鱼

基于 Playwright 浏览器自动化 + Cookie 方式操作闲鱼。

产品能力：
  - 发布「闲置商品」到闲鱼平台
  - 商品包含：标题、描述、价格、图片、分类、成色、发货方式
  - 支持 Cookie 和 Playwright 浏览器自动登录两种方式

登录流程：
  1. 打开 goofish.com → 点击登录 → 跳转淘宝 SSO
  2. 填入淘宝账号密码 → 检测验证码类型
  3. 截图返回 → 用户处理验证码/扫码 → 确认登录
  4. 登录成功 → 保存 Cookie

注意：
  - 淘宝登录有强反爬机制，大概率需要手机扫码
  - 单账号不超过 3次/分钟登录
  - 实际发布商品需对接闲鱼开放平台 API 或 Playwright 模拟
  - 当前版本以登录 + Cookie 管理为主，发布功能为预留

数据字段映射 (Article → 闲鱼商品)：
  Article.title          → 商品标题
  Article.body           → 商品描述
  Article.summary        → 商品卖点摘要
  Article.images         → 商品图片列表
  Article.tags           → 商品标签
  Article.source         → 商品来源平台
  Article.source_url     → 商品原链接
  config.price           → 商品价格（元）
  config.condition       → 商品成色（全新/几乎全新/轻微使用/明显痕迹/残缺）
  config.category        → 商品分类
  config.delivery_method → 发货方式（快递/面交/虚拟）
  config.original_price  → 原价（展示用）
  config.quantity        → 库存数量（默认1）
"""
import re, json, time, random
from typing import Optional
from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError

try:
    from flashsloth.plugins.xianyu_login import XianyuPlaywrightLogin
except ImportError:
    from plugins.xianyu_login import XianyuPlaywrightLogin


# 商品成色选项
CONDITION_OPTIONS = [
    {"value": "new", "label": "全新"},
    {"value": "like_new", "label": "几乎全新"},
    {"value": "slight_use", "label": "轻微使用痕迹"},
    {"value": "obvious_use", "label": "明显使用痕迹"},
    {"value": "damaged", "label": "残缺/配件机"},
]

# 发货方式
DELIVERY_OPTIONS = [
    {"value": "express", "label": "快递"},
    {"value": "in_person", "label": "面交"},
    {"value": "virtual", "label": "虚拟商品"},
]


@register
class XianyuProductsPublisher(Publisher):
    """闲鱼商品发布器 — 发布二手/闲置商品到闲鱼平台"""

    name = "xianyu"
    display_name = "闲鱼"
    login_methods = [
        {"method": "password", "label": "密码+二维码登录", "icon": "🔑", "priority": 1,
         "fields": ["site_url", "username", "password"],
         "description": "输入淘宝账号密码，Playwright 打开登录页处理扫码/验证码"},
        {"method": "cookie", "label": "Cookie 粘贴", "icon": "🍪", "priority": 2,
         "fields": ["site_url", "cookie"],
         "description": "从浏览器 F12 复制 Cookie"},
    ]
    config_fields = [
        {
            "key": "login_mode",
            "label": "登录方式",
            "type": "select",
            "required": True,
            "options": [
                {"value": "cookie", "label": "Cookie 直接访问"},
                {"value": "playwright", "label": "浏览器自动登录（需淘宝账号密码）"},
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
            "placeholder": "淘宝登录密码",
        },
        {
            "key": "cookie",
            "label": "Cookie（Cookie模式）",
            "type": "password",
            "required": False,
            "placeholder": "登录后从浏览器 F12 复制 Cookie",
        },
        # ── 商品默认配置 ──
        {
            "key": "default_price",
            "label": "默认价格（元）",
            "type": "text",
            "required": False,
            "placeholder": "商品默认标价，如 99.00",
        },
        {
            "key": "default_condition",
            "label": "默认成色",
            "type": "select",
            "required": False,
            "options": CONDITION_OPTIONS,
            "placeholder": "选择商品默认成色",
        },
        {
            "key": "default_category",
            "label": "默认分类",
            "type": "text",
            "required": False,
            "placeholder": "商品分类 ID（闲鱼后台分类）",
        },
        {
            "key": "default_delivery",
            "label": "默认发货方式",
            "type": "select",
            "required": False,
            "options": DELIVERY_OPTIONS,
            "placeholder": "选择默认发货方式",
        },
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self.login_mode = config.get("login_mode", "cookie")
        self.taobao_account = config.get("taobao_account", "")
        self.password = config.get("password", "")
        self._login_instance: Optional['XianyuPlaywrightLogin'] = None

        # 商品默认值
        self.default_price = config.get("default_price", "")
        self.default_condition = config.get("default_condition", "slight_use")
        self.default_category = config.get("default_category", "")
        self.default_delivery = config.get("default_delivery", "express")

    def validate_config(self) -> list[str]:
        missing = []
        if self.login_mode == "cookie" and not self.config.get("cookie", ""):
            missing.append("Cookie")
        if self.login_mode == "playwright":
            if not self.taobao_account:
                missing.append("淘宝账号")
            if not self.password:
                missing.append("密码")
        return missing

    def test_connection(self) -> dict:
        """测试连接 — 根据登录方式检查"""
        if self.login_mode == "cookie":
            return self._test_cookie()
        return {
            "success": False,
            "error": "Playwright 模式需先验证验证码才能测试连接",
            "needs_captcha": True,
        }

    def _test_cookie(self) -> dict:
        """测试 Cookie — 模拟访问 goofish.com"""
        cookie = self.config.get("cookie", "")
        if not cookie:
            return {
                "success": False,
                "error": "Cookie 为空，请先登录获取",
                "status": "无 Cookie",
            }
        try:
            import requests
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Cookie": cookie,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }
            resp = requests.get(
                "https://goofish.com", headers=headers, timeout=10,
                allow_redirects=True,
            )
            text = resp.text.lower()
            if resp.status_code == 200:
                user_keywords = ["my", "user", "个人", "我的", "logout", "退出"]
                if any(kw in text for kw in user_keywords):
                    return {"success": True, "error": "", "status": "✅ 已登录"}
                return {
                    "success": True, "error": "",
                    "status": "Cookie 有效，但无法确认登录状态（可能需后续验证）",
                }
            if "login" in resp.url.lower():
                return {"success": False, "error": "Cookie 已过期", "status": "Cookie 过期"}
            return {
                "success": False,
                "error": f"请求异常 (状态码: {resp.status_code})",
                "status": "连接失败",
            }
        except Exception as e:
            return {"success": False, "error": f"连接失败: {e}", "status": "连接失败"}

    # ─── Playwright 浏览器登录 ──────────────────────

    def playwright_login(self) -> dict:
        """使用 Playwright 浏览器自动登录闲鱼

        返回:
            success: bool
            logged_in: bool     — 是否最终登录成功
            needs_captcha: bool — 是否需要验证码/扫码
            image: str          — 截图（base64）
            captcha_type: str   — "qr_scan" | "slider" | "sms" | "none"
            cookies: str        — 登录成功时的 cookie
            error: str
            message: str
        """
        if not self.taobao_account or not self.password:
            return {
                "success": False, "logged_in": False,
                "error": "请先在配置中填写淘宝账号和密码",
            }

        try:
            login = XianyuPlaywrightLogin()
            self._login_instance = login
            result = login.login(
                taobao_account=self.taobao_account,
                password=self.password,
            )

            if result.get("logged_in"):
                cookie_str = result.get("cookies", "")
                self.config["cookie"] = cookie_str

            return result

        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"Playwright 登录异常: {e}",
            }

    def check_playwright_login_status(self) -> dict:
        """检查 Playwright 登录状态（用户处理验证码/扫码后调用）

        返回同 playwright_login()
        """
        try:
            login = self._login_instance or XianyuPlaywrightLogin()
            self._login_instance = login
            result = login.check_login_status()

            if result.get("logged_in"):
                cookie_str = result.get("cookies", "")
                self.config["cookie"] = cookie_str

            return result

        except Exception as e:
            return {
                "success": False, "logged_in": False,
                "error": f"检查登录状态异常: {e}",
            }

    def close_browser(self):
        """关闭 Playwright 浏览器"""
        if self._login_instance:
            try:
                self._login_instance.close()
            except Exception:
                pass
            self._login_instance = None

    def get_cookies(self) -> str:
        """获取当前保存的 cookie"""
        return self.config.get("cookie", "")

    # ─── 商品发布 ──────────────────────────────────

    def publish(self, article: Article, **kwargs) -> dict:
        """发布商品到闲鱼

        Article 字段到商品参数的映射:
            title        → 商品标题（必填，最长 30 字）
            body         → 商品描述（必填，最长 500 字）
            images       → 商品图片（建议 1-9 张）
            price        → 商品价格（通过 kwargs 或 config.default_price）
            condition    → 商品成色
            summary      → 商品卖点/标签

        kwargs 支持:
            price (str/float)    — 价格，如 "99.00"
            condition (str)      — 成色: new/like_new/slight_use/obvious_use/damaged
            category (str)       — 分类 ID
            delivery (str)       — 发货方式: express/in_person/virtual
            quantity (int)       — 库存数量（默认1）
            original_price (str) — 原价（展示用）
            location (str)       — 所在地，如 "上海"
            images (list)        — 图片 URL 列表（覆盖 article.images）
            contact (str)        — 联系方式（可选）

        返回: {"success": bool, "url": str, "id": str, "error": str, "message": str}
        """
        # ── 配置检查 ──
        missing = self.validate_config()
        if missing:
            return {
                "success": False, "url": "", "id": "",
                "error": f"缺少配置: {', '.join(missing)}",
            }

        # Cookie 登录检查
        if self.login_mode == "cookie":
            if not self._has_valid_cookie():
                return {
                    "success": False, "url": "", "id": "",
                    "error": "Cookie 无效或已过期，请重新登录获取",
                }
        elif self.login_mode == "playwright":
            return {
                "success": False, "url": "", "id": "",
                "error": "请先通过 playwright_login() 完成浏览器登录后再发布商品",
            }

        # ── 商品参数准备 ──
        title = article.title.strip()
        if not title:
            return {"success": False, "url": "", "id": "", "error": "商品标题不能为空"}

        if len(title) > 30:
            title = title[:30]

        description = article.body or ""
        if len(description) > 500:
            description = description[:500]

        price = kwargs.get("price", self.default_price or "")
        if not price:
            # 尝试从文章内容提取价格
            price_match = re.search(r'(?:价格|售价|¥|￥)\s*(\d+(?:\.\d{1,2})?)', description)
            if price_match:
                price = price_match.group(1)

        if not price:
            return {
                "success": False, "url": "", "id": "",
                "error": "商品价格不能为空，请通过 kwargs 传入 price 或在配置中设置默认价格",
            }

        product_data = {
            "title": title,
            "description": description,
            "price": str(price),
            "condition": kwargs.get("condition", self.default_condition),
            "category": kwargs.get("category", self.default_category),
            "delivery": kwargs.get("delivery", self.default_delivery),
            "quantity": kwargs.get("quantity", 1),
            "original_price": kwargs.get("original_price", ""),
            "location": kwargs.get("location", ""),
            "contact": kwargs.get("contact", ""),
            "images": kwargs.get("images", article.images or []),
            "summary": article.summary or "",
            "tags": article.tags or [],
        }

        # ── 实际发布 — 使用 Playwright 浏览器模拟 ──
        try:
            from plugins.xianyu_login import XianyuPlaywrightLogin
            login = XianyuPlaywrightLogin()
            login.cookie = self.config.get("cookie", "")
            login._ensure_browser()

            page = login.page
            # 导航到闲鱼首页
            page.goto("https://www.goofish.com", wait_until="domcontentloaded", timeout=30000)
            import time
            time.sleep(2)

            # 导航到发布页面
            page.goto("https://www.goofish.com/publish", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # 填写标题
            title_input = None
            for sel in ["[class*='title'] input", "[class*='Title'] input",
                        "input[placeholder*='标题']", "input[placeholder*='商品']",
                        "textarea[placeholder*='标题']"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        title_input = el
                        break
                except:
                    continue
            if title_input:
                title_input.fill(product_data["title"])

            # 填写价格
            price_input = None
            for sel in ["[class*='price'] input", "input[placeholder*='价格']",
                        "input[placeholder*='¥']", "[class*='Price'] input"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        price_input = el
                        break
                except:
                    continue
            if price_input:
                price_input.fill(product_data["price"])

            # 填写描述
            desc_area = None
            for sel in ["[class*='desc'] textarea", "[class*='describe'] textarea",
                        "textarea[placeholder*='描述']", "textarea[placeholder*='说明']"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        desc_area = el
                        break
                except:
                    continue
            if desc_area:
                desc_area.fill(product_data["description"])

            # 点击提交/发布按钮
            submit_btn = None
            for sel in ["button:has-text('发布')", "button:has-text('提交')",
                        "[class*='submit'] button", "button[class*='publish']"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        submit_btn = el
                        break
                except:
                    continue

            if submit_btn:
                submit_btn.click()
                time.sleep(3)

                # 检查发布结果
                current_url = page.url
                page_text = page.inner_text("body")

                if "成功" in page_text or "发布成功" in page_text or "publish success" in page_text.lower():
                    login.close()
                    return {
                        "success": True, "url": current_url, "id": "",
                        "message": "商品发布成功（需人工确认）",
                    }

                login.close()
                return {
                    "success": True, "url": current_url,
                    "message": "商品发布流程已完成，请到闲鱼确认结果",
                }

            # 没找到提交按钮 — 截图返回让用户确认
            screenshot = login.take_screenshot()
            login.close()
            return {
                "success": False,
                "error": "未找到发布按钮，页面结构可能已变更。请检查截图确认",
                "image": screenshot,
            }

        except ImportError:
            return {
                "success": False,
                "error": "缺少 Playwright 依赖，需要安装: pip install playwright 并安装浏览器",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"发布异常: {e}",
            }

    def _has_valid_cookie(self) -> bool:
        """检查 Cookie 中是否包含关键认证字段"""
        cookie = self.config.get("cookie", "")
        if not cookie:
            return False
        required = ["_tb_token_", "cookie2", "t", "sid", "alimamapwg"]
        return sum(1 for k in required if k in cookie) >= 2

    def __del__(self):
        self.close_browser()
