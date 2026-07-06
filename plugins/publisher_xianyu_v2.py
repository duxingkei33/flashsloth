"""闲鱼 V2 Publisher — 基于 MTOP API 的商品发布器

移植自 goofish-cli 的 MTOP 签名 API 链路，替换原有的 Playwright 脆弱方案。

核心流程：
1. Cookie 导入 / 浏览器自动探测
2. 图片上传到闲鱼 CDN
3. AI 类目识别
4. 默认地址获取
5. MTOP API 发布商品

数据字段映射 (Article → 闲鱼商品)：
  Article.title      → 商品标题（最多30字）
  Article.body       → 商品描述（最多500字）
  Article.images     → 商品图片（建议 1-9 张）
  Article.summary    → 商品卖点
  config.price       → 商品价格（元，必填）
  config.condition   → 商品成色
  config.delivery    → 发货方式
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Literal

from flashsloth.core.article import Article
from flashsloth.core.publisher import Publisher, register, PublishError

from .xianyu_client.session import Session, resolve_cookie_path, write_cookies_json
from .xianyu_client.mtop import call as mtop_call
from .xianyu_client.media import upload_images as upload_media
from .xianyu_client.category import recommend as cat_recommend
from .xianyu_client.location import default_location as get_default_loc
from .xianyu_client.guard import watch as guard_watch
from .xianyu_client.limiter import acquire as limiter_acquire
from .xianyu_client.errors import AuthRequiredError, RiskControlError, RateLimitedError

CONDITION_OPTIONS = [
    {"value": "new", "label": "全新"},
    {"value": "like_new", "label": "几乎全新"},
    {"value": "slight_use", "label": "轻微使用痕迹"},
    {"value": "obvious_use", "label": "明显使用痕迹"},
    {"value": "damaged", "label": "残缺/配件机"},
]

DELIVERY_OPTIONS = [
    {"value": "free", "label": "包邮"},
    {"value": "distance", "label": "按距离计费"},
    {"value": "fixed", "label": "一口价"},
    {"value": "none", "label": "无需邮寄"},
]


@register
class XianyuV2Publisher(Publisher):
    """闲鱼 V2 商品发布器 — 基于 MTOP API（移植 goofish-cli）"""

    name = "xianyu_v2"
    display_name = "闲鱼 V2（MTOP API）"
    login_methods = [
        {"method": "qrcode", "label": "📱 扫码登录", "icon": "📱", "priority": 1,
         "fields": ["site_url"],
         "description": "打开闲鱼/淘宝登录页截图，用手机淘宝扫码后自动捕获 Cookie"},
        {"method": "password", "label": "淘宝账号密码登录", "icon": "🔑", "priority": 2,
         "fields": ["site_url", "username", "password"],
         "description": "输入淘宝账号密码，Playwright 处理扫码/验证码"},
        {"method": "cookie", "label": "Cookie 导入（JSON 格式）", "icon": "🍪", "priority": 99,
         "fields": ["site_url", "cookie"],
         "description": "从浏览器 F12 或 JSON 文件导入闲鱼 Cookie"},
    ]
    config_fields = [
        {
            "key": "site_url", "label": "闲鱼地址", "type": "text", "required": False,
            "default": "https://goofish.com",
        },
        {
            "key": "username", "label": "淘宝账号", "type": "text", "required": False,
            "placeholder": "用于闲鱼登录的淘宝账号",
        },
        {
            "key": "password", "label": "淘宝密码", "type": "password", "required": False,
            "placeholder": "淘宝登录密码",
        },
        {
            "key": "cookie", "label": "Cookie（JSON 格式）", "type": "password",
            "required": False,
            "placeholder": '{"unb":"...", "_m_h5_tk":"...", "cookie2":"..."}',
        },
        {
            "key": "cookie_file", "label": "Cookie 文件路径", "type": "text",
            "required": False,
            "placeholder": "~/.hermes/flashsloth/xianyu_cookies.json",
        },
        {
            "key": "default_price", "label": "默认价格（元）", "type": "text",
            "required": False, "placeholder": "如 99.00",
        },
        {
            "key": "default_condition", "label": "默认成色", "type": "select",
            "required": False, "options": CONDITION_OPTIONS,
            "default": "slight_use",
        },
        {
            "key": "default_delivery", "label": "默认发货方式", "type": "select",
            "required": False, "options": DELIVERY_OPTIONS,
            "default": "none",
        },
        {
            "key": "default_category", "label": "默认分类 ID（可选）", "type": "text",
            "required": False,
            "placeholder": "让 AI 自动识别，或手动填写类目 ID",
        },
    ]

    def __init__(self, config: dict):
        super().__init__(config)
        self._session: Session | None = None

    def _load_session(self) -> Session:
        """加载 Session（优先内存缓存）"""
        if self._session is not None:
            return self._session

        # 1. 尝试从配置的 cookie JSON 字符串加载
        cookie_str = self.config.get("cookie", "")
        if cookie_str:
            try:
                cookies = json.loads(cookie_str) if isinstance(cookie_str, str) else cookie_str
                from requests.cookies import RequestsCookieJar
                http = __import__("requests").Session()
                http.cookies.update(cookies)
                self._session = Session(
                    http=http,
                    unb=cookies.get("unb", ""),
                    tracknick=cookies.get("tracknick", ""),
                    device_id=cookies.get("device_id", ""),
                )
                return self._session
            except (json.JSONDecodeError, Exception) as e:
                raise PublishError(f"Cookie JSON 解析失败：{e}")

        # 2. 尝试从 cookie 文件加载
        cf = self.config.get("cookie_file", "")
        if cf:
            path = resolve_cookie_path(cf if cf else None)
        else:
            path = resolve_cookie_path()

        try:
            self._session = Session.load(path)
            return self._session
        except AuthRequiredError as e:
            raise PublishError(f"闲鱼登录态失效：{e}")

    def validate_config(self) -> list[str]:
        missing = []
        if not self.config.get("cookie") and not self.config.get("cookie_file"):
            # 如果两个都没设，检查默认路径
            if not resolve_cookie_path().exists():
                missing.append("Cookie 或 Cookie 文件路径")
        return missing

    def test_connection(self) -> dict:
        """测试连接 — 尝试加载 Session 并调用一个轻量 API"""
        try:
            session = self._load_session()
            # 用 auth status 类接口测试
            from .xianyu_client.mtop import call
            raw = call(session, api="mtop.taobao.idle.user.minfo.get",
                       data={"userId": session.unb}, version="1.0",
                       timeout=15)
            return {
                "success": True,
                "status": f"已登录 (unb={session.unb})",
            }
        except AuthRequiredError as e:
            return {"success": False, "error": f"登录态失效：{e}", "status": "需重新登录"}
        except RiskControlError as e:
            return {"success": False, "error": f"触发风控：{e}", "status": "风控中"}
        except Exception as e:
            return {"success": False, "error": f"连接失败：{e}", "status": "连接失败"}

    # ─── Cookie 管理 ──────────────────────────────

    def import_cookie(self, cookie_data: str | dict, save: bool = True) -> dict:
        """导入 Cookie

        cookie_data: JSON 字符串或 dict
        save: 是否保存到文件
        """
        if isinstance(cookie_data, str):
            cookies = json.loads(cookie_data)
        else:
            cookies = cookie_data

        if "unb" not in cookies or "_m_h5_tk" not in cookies:
            return {"success": False, "error": "Cookie 缺失 unb / _m_h5_tk 关键字段"}

        if save:
            path = resolve_cookie_path()
            write_cookies_json(path, cookies)

        # 重置 session 缓存
        self._session = None
        result = {
            "success": True,
            "message": f"Cookie 已导入 (unb={cookies.get('unb')})",
        }
        if save:
            result["path"] = str(path)
        return result

    def export_cookie(self) -> dict:
        """导出当前 Cookie"""
        try:
            session = self._load_session()
            return {"success": True, "cookies": session.to_dict(), "unb": session.unb}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ─── 商品发布（核心） ────────────────────────

    def publish(self, article: Article, **kwargs) -> dict:
        """发布商品到闲鱼（MTOP API）

        kwargs 支持:
            price (str/float)      — 价格（必填）
            condition (str)       — 成色: new/like_new/slight_use/obvious_use/damaged
            delivery (str)        — 发货方式: free/distance/fixed/none
            post_price (float)    — 运费（仅 fixed 模式）
            can_self_pickup (bool)— 是否支持自提（默认 True）
            original_price (float)— 原价（展示用）
            images (list)         — 图片本地路径列表
            category (str)        — 强制指定类目 ID（跳过 AI 识别）
        """
        # ── 1. 准备 Session ──
        try:
            session = self._load_session()
        except PublishError:
            raise
        except Exception as e:
            return {"success": False, "url": "", "id": "", "error": f"Session 加载失败：{e}"}

        # ── 2. 参数准备 ──
        title = (article.title or "").strip()
        if not title:
            return {"success": False, "url": "", "id": "", "error": "商品标题不能为空"}
        if len(title) > 30:
            title = title[:30]

        desc = (article.body or "")[:500]
        price = kwargs.get("price", self.config.get("default_price", ""))
        if not price:
            return {
                "success": False, "url": "", "id": "", "error": "商品价格不能为空"
            }

        delivery = kwargs.get("delivery", self.config.get("default_delivery", "none"))
        post_price = float(kwargs.get("post_price", 0))
        can_self_pickup = kwargs.get("can_self_pickup", True)
        original_price = kwargs.get("original_price", None)
        force_category = kwargs.get("category", self.config.get("default_category", ""))

        # 图片路径
        image_paths = kwargs.get("images", article.images or [])

        # ── 3. 上传图片 ──
        image_infos: list[dict[str, Any]] = []
        if image_paths:
            for img_path in image_paths:
                with limiter_acquire("item.write"):
                    r = upload_media(img_path, session)
                image_infos.append({
                    "url": r["url"],
                    "width": r["width"],
                    "height": r["height"],
                })

        # ── 4. 类目识别（或跳过） ──
        if force_category:
            cat_info = {
                "cat_id": force_category,
                "cat_name": "",
                "channel_cat_id": "",
                "tb_cat_id": "",
            }
        else:
            with limiter_acquire("item.write"):
                try:
                    cat_info = cat_recommend(title, image_infos, session)
                except Exception as e:
                    # AI 识别失败，用空类目让闲鱼自动分配
                    cat_info = {"cat_id": "", "cat_name": "", "channel_cat_id": "", "tb_cat_id": ""}

        # ── 5. 默认地址 ──
        try:
            loc = get_default_loc(session=session)
        except Exception:
            loc = {"prov": "", "city": "", "area": "", "poi": "", "division_id": "", "all": []}

        # ── 6. 构建发布数据 ──
        data = self._build_publish_data(
            title=title, desc=desc, image_infos=image_infos,
            price=float(price), original_price=float(original_price) if original_price else None,
            delivery=delivery, post_price=post_price, can_self_pickup=can_self_pickup,
            cat_info=cat_info, location=loc,
        )

        # ── 7. 发布（写操作，走熔断） ──
        with limiter_acquire("item.write"), guard_watch():
            raw = mtop_call(
                session,
                api="mtop.idle.pc.idleitem.publish",
                data=data,
                version="1.0",
                spm_cnt="a21ybx.publish.0.0",
            )

        data_out = raw.get("data", {}) or {}
        ok = any("SUCCESS" in r for r in raw.get("ret", []))

        if ok:
            item_id = data_out.get("itemId", "")
            return {
                "success": True,
                "url": f"https://www.goofish.com/item/{item_id}" if item_id else "",
                "id": item_id,
                "message": f"商品发布成功！ID: {item_id}",
            }
        else:
            return {
                "success": False,
                "url": "", "id": "",
                "error": f"发布失败: {raw.get('ret', [])}",
            }

    def _build_publish_data(
        self, *, title: str, desc: str,
        image_infos: list[dict[str, Any]],
        price: float, original_price: float | None,
        delivery: str, post_price: float,
        can_self_pickup: bool,
        cat_info: dict[str, Any],
        location: dict[str, Any],
    ) -> dict[str, Any]:
        """构建 MTOP 发布数据（与 goofish-cli 一致）"""
        image_do_list = [
            {
                "extraInfo": {"isH": "false", "isT": "false", "raw": "false"},
                "isQrCode": False,
                "url": img["url"],
                "heightSize": img["height"],
                "widthSize": img["width"],
                "major": True,
                "type": 0,
                "status": "done",
            }
            for img in image_infos
        ]

        post_fee: dict[str, Any] = {
            "canFreeShipping": False,
            "supportFreight": False,
            "onlyTakeSelf": False,
        }
        if delivery == "free":
            post_fee["canFreeShipping"] = True
            post_fee["supportFreight"] = True
        elif delivery == "distance":
            post_fee["supportFreight"] = True
            post_fee["templateId"] = "-100"
        elif delivery == "fixed":
            post_fee["supportFreight"] = True
            post_fee["postPriceInCent"] = str(int(post_price * 100))
            post_fee["templateId"] = "0"
        elif delivery == "none":
            post_fee["templateId"] = "0"

        price_dto: dict[str, str] = {}
        default_price = price <= 0
        if not default_price:
            price_dto["priceInCent"] = str(int(price * 100))
        if original_price and original_price > 0:
            price_dto["origPriceInCent"] = str(int(original_price * 100))

        item_addr: dict[str, Any] = {}
        if location.get("division_id"):
            all_addrs = location.get("all", []) or []
            first = all_addrs[0] if all_addrs else {}
            item_addr = {
                "area": first.get("area", ""),
                "city": first.get("city", ""),
                "divisionId": first.get("divisionId", ""),
                "gps": f"{first.get('longitude', '')},{first.get('latitude', '')}",
                "poiId": first.get("poiId", ""),
                "poiName": first.get("poi", ""),
                "prov": first.get("prov", ""),
            }

        return {
            "freebies": False,
            "itemTypeStr": "b",
            "quantity": "1",
            "simpleItem": "true",
            "imageInfoDOList": image_do_list,
            "itemTextDTO": {"desc": desc, "title": title, "titleDescSeparate": True},
            "itemLabelExtList": [],
            "itemPriceDTO": price_dto,
            "userRightsProtocols": [{"enable": False, "serviceCode": "SKILL_PLAY_NO_MIND"}],
            "itemPostFeeDTO": post_fee,
            "itemAddrDTO": item_addr,
            "defaultPrice": default_price,
            "itemCatDTO": {
                "catId": cat_info.get("cat_id", ""),
                "catName": cat_info.get("cat_name", ""),
                "channelCatId": cat_info.get("channel_cat_id", ""),
                "tbCatId": cat_info.get("tb_cat_id", ""),
            },
            "onlyTakeSelf": can_self_pickup,
            "uniqueCode": "1775897582791680",
            "sourceId": "pcMainPublish",
            "bizcode": "pcMainPublish",
            "publishScene": "pcMainPublish",
        }

    # ─── 商品管理 ──────────────────────────────

    def publish_draft(self, article: Article, **kwargs) -> dict:
        """存草稿 — 对于闲鱼，存草稿 = 不上传、不发布，只返回构建的数据"""
        return {
            "success": True,
            "message": "闲鱼不支持存草稿 API，数据已准备好（未执行发布）",
            "product_data": json.dumps(self._build_publish_data(
                title=article.title[:30] if article.title else "",
                desc=(article.body or "")[:500],
                image_infos=[],
                price=float(kwargs.get("price", 0)),
                original_price=None,
                delivery=kwargs.get("delivery", "none"),
                post_price=0, can_self_pickup=True,
                cat_info={"cat_id": "", "cat_name": "", "channel_cat_id": "", "tb_cat_id": ""},
                location={"division_id": "", "all": []},
            ), ensure_ascii=False),
        }

    def retract(self, item_id: str, **kwargs) -> dict:
        """下架商品（框架预留，需闲鱼 API 支持）"""
        return {"success": False, "error": "闲鱼 MTOP API 暂不支持通过 API 下架商品"}

    def get_item(self, item_id: str) -> dict:
        """获取商品详情"""
        try:
            session = self._load_session()
            raw = mtop_call(
                session,
                api="mtop.idle.pc.idleitem.detail",
                data={"itemId": str(item_id)},
                version="1.0",
            )
            return {"success": True, "data": raw.get("data", {})}
        except Exception as e:
            return {"success": False, "error": str(e)}
