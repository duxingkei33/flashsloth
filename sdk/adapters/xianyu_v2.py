"""
闲鱼 (Xianyu / goofish.com) API v2 适配器

从 XianyuAutoAgent (github.com/shaxiu/XianyuAutoAgent) 蒸馏提取核心API层，
集成到 FlashSloth SDK 体系。

能力：
  - login()              Cookie登录 + 状态检测
  - get_item_info()      获取商品详情(含价格/库存/SKU)
  - search_products()    搜索商品(关键词/价格范围/排序)
  - get_token()          刷新Token
  - price_monitor()      价格监控(注册监控任务)

依赖: requests, 需配置 Cookie
"""
import json, time, hashlib, base64, random, re, os
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

import requests


# ═══════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════

@dataclass
class XianyuProduct:
    """闲鱼商品统一模型"""
    item_id: str = ""
    title: str = ""
    desc: str = ""
    price: float = 0.0          # 现价(元)
    original_price: float = 0.0  # 原价(元)
    sold_price: float = 0.0      # 成交价
    images: list = field(default_factory=list)
    sku_list: list = field(default_factory=list)  # [{"spec":"...", "price":0, "stock":0}]
    stock: int = 0
    sales: int = 0
    seller_id: str = ""
    seller_name: str = ""
    seller_credit: int = 0       # 卖家信誉分
    location: str = ""           # 所在地
    status: str = "active"       # active | sold | paused
    url: str = ""
    created_at: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class PriceAlert:
    """价格监控报警"""
    keyword: str = ""
    target_price: float = 0.0
    current_price: float = 0.0
    product: XianyuProduct = None
    matched_at: str = ""


# ═══════════════════════════════════════════════
# 工具函数（从 XianyuAutoAgent 提取）
# ═══════════════════════════════════════════════

def _parse_cookies(cookies_str: str) -> dict:
    """解析 Cookie 字符串为字典"""
    result = {}
    for cookie in cookies_str.split("; "):
        try:
            parts = cookie.split("=", 1)
            if len(parts) == 2:
                result[parts[0]] = parts[1]
        except Exception:
            continue
    return result


def _generate_mid() -> str:
    """生成消息 ID"""
    rand_part = int(1000 * random.random())
    ts = int(time.time() * 1000)
    return f"{rand_part}{ts} 0"


def _generate_uuid() -> str:
    return f"-{int(time.time() * 1000)}1"


def _generate_device_id(user_id: str) -> str:
    """生成设备 ID"""
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    result = []
    for i in range(36):
        if i in [8, 13, 18, 23]:
            result.append("-")
        elif i == 14:
            result.append("4")
        else:
            if i == 19:
                result.append(chars[(int(16 * random.random()) & 0x3) | 0x8])
            else:
                result.append(chars[int(16 * random.random())])
    return "".join(result) + "-" + user_id


def _generate_sign(t: str, token: str, data: str) -> str:
    """生成闲鱼API签名 (MD5)"""
    app_key = "34839810"
    msg = f"{token}&{t}&{app_key}&{data}"
    return hashlib.md5(msg.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════
# API 客户端
# ═══════════════════════════════════════════════

class XianyuApiV2:
    """
    闲鱼 API v2 客户端

    用法:
        api = XianyuApiV2(cookie_string)
        api.login()
        info = api.get_item_info("123456")
        results = api.search_products("树莓派5", max_price=500)
    """

    # API 基础地址
    H5API = "https://h5api.m.goofish.com/h5"
    PASSPORT = "https://passport.goofish.com"
    GOOFISH = "https://www.goofish.com"

    def __init__(self, cookies_str: str = ""):
        self.session = requests.Session()
        self.session.headers.update({
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
            "origin": self.GOOFISH,
            "referer": f"{self.GOOFISH}/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/133.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })
        if cookies_str:
            self.set_cookies(cookies_str)
        self._device_id = None
        self._user_id = None

    # ─── Cookie 管理 ───────────────────────────

    def set_cookies(self, cookies_str: str):
        """设置 Cookie 字符串"""
        from http.cookies import SimpleCookie
        try:
            cookie = SimpleCookie()
            cookie.load(cookies_str)
            for key, morsel in cookie.items():
                self.session.cookies.set(key, morsel.value)
        except Exception:
            # fallback: 手动解析
            for k, v in _parse_cookies(cookies_str).items():
                self.session.cookies.set(k, v)
        self._user_id = self.session.cookies.get("unb", "")
        self._device_id = _generate_device_id(self._user_id) if self._user_id else None

    def get_cookies_str(self) -> str:
        """获取当前 Cookie 字符串"""
        return "; ".join(
            f"{c.name}={c.value}" for c in self.session.cookies
        )

    # ─── 登录检测 ───────────────────────────

    def has_login(self, retry_count=0) -> bool:
        """检测是否已登录"""
        if retry_count >= 2:
            return False
        try:
            params = {"appName": "xianyu", "fromSite": "77"}
            data = {
                "hid": self.session.cookies.get("unb", ""),
                "ltl": "true",
                "appName": "xianyu",
                "appEntrance": "web",
                "_csrf_token": self.session.cookies.get("XSRF-TOKEN", ""),
                "umidToken": "",
                "hsiz": self.session.cookies.get("cookie2", ""),
                "bizParams": "taobaoBizLoginFrom=web",
                "mainPage": "false",
                "isMobile": "false",
                "lang": "zh_CN",
                "returnUrl": "",
                "fromSite": "77",
                "isIframe": "true",
                "documentReferer": f"{self.GOOFISH}/",
                "defaultView": "hasLogin",
                "umidTag": "SERVER",
                "deviceId": self.session.cookies.get("cna", ""),
            }
            resp = self.session.post(
                f"{self.PASSPORT}/newlogin/hasLogin.do",
                params=params, data=data, timeout=15
            )
            result = resp.json()
            if result.get("content", {}).get("success"):
                self._clear_duplicate_cookies()
                return True
            time.sleep(0.5)
            return self.has_login(retry_count + 1)
        except Exception as e:
            print("[Xianyu] hasLogin failed: {e}")
            time.sleep(0.5)
            return self.has_login(retry_count + 1)

    def _clear_duplicate_cookies(self):
        """清理重复 Cookie"""
        new_jar = requests.cookies.RequestsCookieJar()
        added = set()
        cookie_list = list(self.session.cookies)
        cookie_list.reverse()
        for cookie in cookie_list:
            if cookie.name not in added:
                new_jar.set_cookie(cookie)
                added.add(cookie.name)
        self.session.cookies = new_jar

    # ─── Token 管理 ───────────────────────────

    def get_token(self, retry_count=0) -> Optional[str]:
        """获取/刷新 accessToken"""
        if retry_count >= 2:
            # 尝试重新登录
            if self.has_login():
                return self.get_token(0)
            print("[Xianyu] ERR")
            return None

        ts = str(int(time.time() * 1000))
        data_val = json.dumps({
            "appKey": "444e9908a51d1cb236a27862abc769c9",
            "deviceId": self._device_id or "",
        }, separators=(",", ":"))

        token = self.session.cookies.get("_m_h5_tk", "").split("_")[0]
        sign = _generate_sign(ts, token, data_val)

        params = {
            "jsv": "2.7.2", "appKey": "34839810", "t": ts,
            "sign": sign, "v": "1.0", "type": "originaljson",
            "accountSite": "xianyu", "dataType": "json", "timeout": "20000",
            "api": "mtop.taobao.idlemessage.pc.login.token",
            "sessionOption": "AutoLoginOnly",
        }

        try:
            resp = self.session.post(
                f"{self.H5API}/mtop.taobao.idlemessage.pc.login.token/1.0/",
                params=params, data={"data": data_val}, timeout=15
            )
            result = resp.json()
            ret = result.get("ret", [])
            if any("SUCCESS" in r for r in ret):
                return result.get("data", {}).get("accessToken")
            print("[Xianyu] WARN")
            time.sleep(0.5)
            return self.get_token(retry_count + 1)
        except Exception as e:
            print("[Xianyu] WARN")
            time.sleep(0.5)
            return self.get_token(retry_count + 1)

    # ─── 商品详情 ───────────────────────────

    def get_item_info(self, item_id: str, retry_count=0) -> Optional[XianyuProduct]:
        """
        获取商品详情。
        返回 XianyuProduct 对象，失败返回 None。
        """
        if retry_count >= 3:
            return None

        ts = str(int(time.time() * 1000))
        data_val = json.dumps({"itemId": item_id}, separators=(",", ":"))
        token = self.session.cookies.get("_m_h5_tk", "").split("_")[0]
        sign = _generate_sign(ts, token, data_val)

        params = {
            "jsv": "2.7.2", "appKey": "34839810", "t": ts,
            "sign": sign, "v": "1.0", "type": "originaljson",
            "accountSite": "xianyu", "dataType": "json", "timeout": "20000",
            "api": "mtop.taobao.idle.pc.detail",
            "sessionOption": "AutoLoginOnly",
        }

        try:
            resp = self.session.post(
                f"{self.H5API}/mtop.taobao.idle.pc.detail/1.0/",
                params=params, data={"data": data_val}, timeout=15
            )
            result = resp.json()
            ret = result.get("ret", [])
            if not any("SUCCESS" in r for r in ret):
                # 检查 Set-Cookie
                if "Set-Cookie" in resp.headers:
                    self._clear_duplicate_cookies()
                time.sleep(0.5)
                return self.get_item_info(item_id, retry_count + 1)

            item_do = result.get("data", {}).get("itemDO", {})
            return self._parse_item(item_do)

        except Exception as e:
            print("[Xianyu] WARN")
            time.sleep(0.5)
            return self.get_item_info(item_id, retry_count + 1)

    # ─── 商品搜索 ───────────────────────────

    def search_products(
        self,
        keyword: str,
        min_price: float = 0,
        max_price: float = 0,
        sort_by: str = "default",     # default | price_asc | price_desc | time
        page: int = 1,
        page_size: int = 20,
    ) -> list[XianyuProduct]:
        """
        搜索闲鱼商品。

        参数:
            keyword: 搜索关键词
            min_price: 最低价(0=不限)
            max_price: 最高价(0=不限)
            sort_by: 排序方式
            page: 页码
            page_size: 每页数量
        返回:
            XianyuProduct 列表
        """
        # 闲鱼搜索使用 H5 搜索 API
        search_url = f"{self.GOOFISH}/search"
        params = {
            "keyword": keyword,
            "page": page,
            "pageSize": page_size,
        }
        if min_price > 0:
            params["minPrice"] = min_price
        if max_price > 0:
            params["maxPrice"] = max_price

        sort_map = {
            "default": "default",
            "price_asc": "price_asc",
            "price_desc": "price_desc",
            "time": "time",
        }
        params["sort"] = sort_map.get(sort_by, "default")

        try:
            resp = self.session.get(search_url, params=params, timeout=15)
            data = resp.json()
            items = data.get("data", {}).get("items", [])
            results = []
            for item in items:
                results.append(XianyuProduct(
                    item_id=str(item.get("itemId", "")),
                    title=item.get("title", ""),
                    price=float(item.get("price", 0)) / 100,
                    original_price=float(item.get("originalPrice", 0)) / 100,
                    sold_price=float(item.get("soldPrice", 0)) / 100,
                    images=item.get("images", []),
                    stock=item.get("quantity", 0),
                    sales=item.get("sales", 0),
                    seller_id=item.get("sellerId", ""),
                    seller_name=item.get("sellerNick", ""),
                    location=item.get("location", ""),
                    url=f"{self.GOOFISH}/item/{item.get('itemId', '')}",
                    status="active" if item.get("status") == 0 else "sold",
                    raw=item,
                ))
            return results
        except Exception as e:
            print("[Xianyu] WARN")
            return []

    # ─── 内部工具 ───────────────────────────

    def _parse_item(self, item_do: dict) -> XianyuProduct:
        """解析商品详情DO为XianyuProduct"""
        def fmt_price(p):
            try:
                return round(float(p) / 100, 2)
            except (ValueError, TypeError):
                return 0.0

        sku_list = []
        for sku in item_do.get("skuList", []):
            specs = [p.get("valueText", "") for p in sku.get("propertyList", [])]
            sku_list.append({
                "spec": " ".join(specs) if specs else "默认规格",
                "price": fmt_price(sku.get("price", 0)),
                "stock": sku.get("quantity", 0),
            })

        return XianyuProduct(
            item_id=str(item_do.get("itemId", "")),
            title=item_do.get("title", ""),
            desc=item_do.get("desc", ""),
            price=fmt_price(item_do.get("price", 0)),
            sold_price=fmt_price(item_do.get("soldPrice", 0)),
            images=item_do.get("images", []),
            sku_list=sku_list,
            stock=item_do.get("quantity", 0),
            sales=item_do.get("sales", 0),
            seller_id=item_do.get("sellerId", ""),
            seller_name=item_do.get("sellerNick", ""),
            location=item_do.get("location", ""),
            url=f"{self.GOOFISH}/item/{item_do.get('itemId', '')}",
            raw=item_do,
        )


# ═══════════════════════════════════════════════
# 快捷使用
# ═══════════════════════════════════════════════

def create_client(cookies_str: str = "") -> XianyuApiV2:
    """创建已登录的闲鱼API客户端"""
    client = XianyuApiV2(cookies_str)
    if cookies_str:
        client.has_login()
    return client
