"""
FlashSloth 统一 Cookie 验证器

消除以下散落代码的重复：
  - core/credential_provider.py  _check_auth_cookies()      ← Playwright cookies list 校验
  - routes/accounts.py          _check_auth_cookies()      ← 同上但更旧（缺 wechat）
  - sdk/adapters/oshwhub.py     _has_valid_cookie()        ← oshwhub 自研
  - core/status_detector.py     PLATFORM_DETECTORS         ← API 级校验注册表

用法:
    # Playwright cookies list 输入
    from flashsloth.core.cookie_validator import verify_cookie
    cookies = page.context.cookies()
    result = verify_cookie("bilibili", cookies, input_type="list")

    # Cookie 字符串输入
    result = verify_cookie("zhihu", "z_c0=xxx; d_c0=yyy", input_type="string")

    # 自动检测输入类型
    result = verify_cookie("oshwhub", cookie_str)
"""

import re
import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _cookie_list_to_map(cookies: list) -> dict:
    """将 Playwright cookies() 列表转换为 {name: value} 字典"""
    return {c["name"]: c.get("value", "") for c in cookies}


def _cookie_str_to_map(cookie_str: str) -> dict:
    """将 "; " 分隔的 Cookie 字符串转换为 {name: value} 字典"""
    result = {}
    if not cookie_str:
        return result
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        result[n.strip()] = v.strip()
    return result


def _cookie_str_to_list(cookie_str: str) -> list:
    """将 "; " 分隔的 Cookie 字符串转换为 Playwright 风格的 list[dict]"""
    if not cookie_str:
        return []
    result = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        n, v = pair.split("=", 1)
        result.append({"name": n.strip(), "value": v.strip()})
    return result


def _cookie_list_to_str(cookies: list) -> str:
    """将 Playwright cookies() 列表转换为 "; " 分隔的字符串"""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def _detect_input_type(cookie_input: Any) -> str:
    """自动检测输入是 'string' 还是 'list'"""
    if isinstance(cookie_input, str):
        return "string"
    if isinstance(cookie_input, (list, tuple)):
        # 检查是否像 Playwright cookies list
        cookie_input = list(cookie_input)
        if cookie_input and isinstance(cookie_input[0], dict):
            return "list"
        return "string"
    return "string"  # fallback


def _normalize_to_map(cookie_input: Any, input_type: str) -> dict:
    """统一将输入转换为 {name: value} 字典"""
    if input_type == "list":
        if isinstance(cookie_input, str):
            return _cookie_str_to_map(cookie_input)
        return _cookie_list_to_map(list(cookie_input) if isinstance(cookie_input, (list, tuple)) else [])
    return _cookie_str_to_map(str(cookie_input) if not isinstance(cookie_input, str) else cookie_input)


def _normalize_to_str(cookie_input: Any, input_type: str) -> str:
    """统一将输入转换为 "; " 分隔的 Cookie 字符串"""
    if input_type == "list":
        if isinstance(cookie_input, str):
            return cookie_input
        return _cookie_list_to_str(list(cookie_input) if isinstance(cookie_input, (list, tuple)) else [])
    return str(cookie_input) if not isinstance(cookie_input, str) else cookie_input


def _make_session():
    """创建带基本 UA 的 requests Session"""
    import requests
    sess = requests.Session()
    sess.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return sess


# ═══════════════════════════════════════════════════════════════
# Phase 1: Keyword-level handlers（无网络，仅检查 Cookie 键/值特征）
# ═══════════════════════════════════════════════════════════════

def _keyword_bilibili(cookie_map: dict) -> dict:
    """B站需要同时存在三个认证 Cookie"""
    required = ["bili_jct", "SESSDATA", "DedeUserID"]
    if all(k in cookie_map for k in required):
        return {"valid": True, "message": "B站认证 Cookie 完整"}
    missing = [k for k in required if k not in cookie_map]
    return {"valid": False, "message": f"B站缺少认证 Cookie: {', '.join(missing)}"}


def _keyword_discuz(cookie_map: dict) -> dict:
    """Discuz/Amobbs 需要 auth cookie 值非空"""
    auth_val = cookie_map.get("auth", "")
    if auth_val and auth_val.strip():
        return {"valid": True, "message": "Discuz auth Cookie 有效"}
    return {"valid": False, "message": "Discuz 缺少 auth Cookie 或值为空"}


def _keyword_amobbs(cookie_map: dict) -> dict:
    """Amobbs 同 Discuz，需要 auth cookie"""
    return _keyword_discuz(cookie_map)


def _keyword_wechat(cookie_map: dict) -> dict:
    """微信/公众号平台需要特定 Cookie 之一"""
    wx_keys = ["token", "fakeid", "slave_user", "slave_sid"]
    for k in wx_keys:
        if k in cookie_map and cookie_map[k].strip():
            return {"valid": True, "message": f"微信认证 Cookie 存在: {k}"}
    return {"valid": False, "message": "微信缺少认证 Cookie (token/fakeid/slave_user/slave_sid)"}


def _keyword_oshwhub(cookie_map: dict) -> dict:
    """立创开源硬件平台 oshwhub 专有校验

    两阶段匹配：
    Phase 1 (精确): 已知的 OSHWHub/嘉立创认证 cookie 名精确匹配
    Phase 2 (松散): 关键字包含匹配兜底
    """
    # Phase 1: 精确匹配已知认证 cookie 名
    precise_keys = [
        "remember_user", "user_name", "username", "nickname", "uname",
        "jlc_user", "jlc_token", "jlc_sid", "jlc_uid", "jlc_auth",
        "oshwhub_user", "oshwhub_token", "oshwhub_auth",
        "identity", "sessionid", "sid",
    ]
    for k, v in cookie_map.items():
        if k in precise_keys and v.strip():
            return {"valid": True, "message": f"OSHWHub 认证 Cookie 存在: {k}"}
    # Phase 2: 松散关键字包含匹配（兜底）
    oshw_keys = ["auth", "token", "session", "oshwhub", "identity",
                  "user_name", "username", "nickname", "uname", "remember_user"]
    for k, v in cookie_map.items():
        kl = k.lower()
        if any(kw in kl for kw in oshw_keys) and v.strip():
            return {"valid": True, "message": f"OSHWHub 认证 Cookie 存在: {k}"}
    return {"valid": False, "message": "OSHWHub 未检测到认证 Cookie"}


def _keyword_csdn(cookie_map: dict) -> dict:
    """CSDN 认证 Cookie 特征"""
    csdn_keys = ["UserName", "username", "login_name", "uname",
                 "SESSION", "CASTGC", "TGC", "user_info"]
    for k, v in cookie_map.items():
        if k in csdn_keys and v.strip():
            return {"valid": True, "message": f"CSDN 认证 Cookie 存在: {k}"}
    return {"valid": False, "message": "CSDN 未检测到认证 Cookie"}


def _keyword_zhihu(cookie_map: dict) -> dict:
    """知乎认证 Cookie 特征：z_c0 或 d_c0 为登录凭证"""
    for key in ["z_c0", "d_c0"]:
        if key in cookie_map and cookie_map[key].strip():
            return {"valid": True, "message": f"知乎认证 Cookie 存在: {key}"}
    return {"valid": False, "message": "知乎缺少认证 Cookie (z_c0/d_c0)"}


def _keyword_juejin(cookie_map: dict) -> dict:
    """掘金认证 Cookie 特征"""
    for key in ["sessionid", "USER_SESSION", "monad", "SESSION"]:
        if key in cookie_map and cookie_map[key].strip():
            return {"valid": True, "message": f"掘金认证 Cookie 存在: {key}"}
    return {"valid": False, "message": "掘金缺少认证 Cookie (sessionid/USER_SESSION/monad)"}


def _keyword_xianyu(cookie_map: dict) -> dict:
    """闲鱼认证 Cookie 特征"""
    xianyu_keys = ["_m_h5_tk", "unb", "cookie2", "sld", "mtop_trace",
                   "x5sec", "session", "sid"]
    for k, v in cookie_map.items():
        kl = k.lower()
        if any(kw in kl for kw in xianyu_keys) and v.strip():
            return {"valid": True, "message": f"闲鱼认证 Cookie 存在: {k}"}
    return {"valid": False, "message": "闲鱼未检测到认证 Cookie"}


def _keyword_wordpress(cookie_map: dict) -> dict:
    """WordPress 认证 Cookie 特征"""
    wp_keys = ["wordpress_logged_in", "wordpress_sec", "wp-settings",
               "auth", "token", "session"]
    for k, v in cookie_map.items():
        if k in wp_keys and v.strip():
            return {"valid": True, "message": f"WordPress 认证 Cookie 存在: {k}"}
    # 通用兜底
    auth_kw = ["auth", "token", "session", "login", "passport"]
    for k, v in cookie_map.items():
        kl = k.lower()
        if any(kw in kl for kw in auth_kw) and v.strip():
            return {"valid": True, "message": f"WordPress 认证 Cookie 存在: {k}"}
    return {"valid": False, "message": "WordPress 未检测到认证 Cookie"}


def _keyword_fallback(cookie_map: dict) -> dict:
    """通用兜底：检查是否有任意认证关键字 Cookie"""
    auth_kw = ["auth", "token", "session", "login", "passport"]
    for k, v in cookie_map.items():
        if any(kw in k.lower() for kw in auth_kw) and v.strip():
            return {"valid": True, "message": f"检测到认证 Cookie: {k}"}
    return {"valid": False, "message": "未检测到任何认证 Cookie"}


# ═══════════════════════════════════════════════════════════════
# Phase 2: API-level handlers（网络请求，深度验证）
# 复用 status_detector 现有检测逻辑，统一返回值格式
# ═══════════════════════════════════════════════════════════════

def _api_discuz(cookie_str: str, site_url: str) -> dict:
    """通过 Discuz 个人资料页验证 Cookie"""
    from flashsloth.core.status_detector import detect_discuz
    return detect_discuz(site_url, cookie_str, "discuz")


def _api_amobbs(cookie_str: str, site_url: str) -> dict:
    from flashsloth.core.status_detector import detect_discuz
    return detect_discuz(site_url, cookie_str, "amobbs")


def _api_csdn(cookie_str: str, **kwargs) -> dict:
    from flashsloth.core.status_detector import detect_csdn
    return detect_csdn(cookie_str)


def _api_oshwhub(cookie_str: str, username_hint: str = "") -> dict:
    from flashsloth.core.status_detector import detect_oshwhub
    return detect_oshwhub(cookie_str, username_hint)


def _api_zhihu(cookie_str: str, **kwargs) -> dict:
    from flashsloth.core.status_detector import detect_zhihu
    return detect_zhihu(cookie_str)


def _api_juejin(cookie_str: str, **kwargs) -> dict:
    from flashsloth.core.status_detector import detect_juejin
    return detect_juejin(cookie_str)


def _api_xianyu(cookie_str: str, **kwargs) -> dict:
    from flashsloth.core.status_detector import detect_xianyu
    return detect_xianyu(cookie_str)


def _api_bilibili(cookie_str: str, **kwargs) -> dict:
    """B站 API 级验证：访问 nav API"""
    result = {"logged_in": False, "method": "api_lightweight",
              "platform": "bilibili", "site_url": "https://www.bilibili.com"}
    try:
        sess = _make_session()
        for name, value in _cookie_str_to_map(cookie_str).items():
            sess.cookies.set(name, value)
        resp = sess.get(
            "https://api.bilibili.com/x/web-interface/nav",
            timeout=10,
            headers={"Referer": "https://www.bilibili.com/"},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("isLogin"):
                user = data["data"]
                result["logged_in"] = True
                result["username"] = user.get("uname", "")
                result["display_name"] = user.get("uname", "")
                result["points"] = user.get("level_info", {}).get("current_level", 0)
                result["level"] = f"Lv.{result['points']}" if result["points"] else ""
                result["avatar_url"] = user.get("face", "")
                result["verified_at"] = datetime.now().isoformat()
                result["status"] = f"✅ {result['username']} (Lv.{result['points']})"
                return result
        result["error"] = "B站API返回未登录"
        result["status"] = "❌ Cookie未登录（B站API检测）"
    except Exception as e:
        result["error"] = str(e)[:200]
        result["status"] = f"⚠️ API检测异常: {str(e)[:80]}"
    return result


def _api_wechat(cookie_str: str, **kwargs) -> dict:
    """微信公众号 API 级验证"""
    result = {"logged_in": False, "method": "api_lightweight",
              "platform": "wechat", "site_url": "https://mp.weixin.qq.com"}
    try:
        sess = _make_session()
        for name, value in _cookie_str_to_map(cookie_str).items():
            sess.cookies.set(name, value)
        resp = sess.get("https://mp.weixin.qq.com/", timeout=15, allow_redirects=True)
        html = resp.text
        username = ""
        name_patterns = [
            r'"nick_name"\s*:\s*"([^"]+)"',
            r'"username"\s*:\s*"([^"]+)"',
            r'"fakeid"\s*:\s*"([^"]+)"',
            r'<span[^>]*class="[^"]*account_name[^"]*"[^>]*>([^<]+)',
        ]
        for pat in name_patterns:
            m = re.search(pat, html)
            if m:
                username = m.group(1).strip()
                if username and len(username) >= 2:
                    break
        logged_in = bool(username)
        result["logged_in"] = logged_in
        result["username"] = username or ""
        result["display_name"] = username or ""
        result["verified_at"] = datetime.now().isoformat()
        if logged_in:
            result["status"] = f"✅ {username}（微信公众号）"
        else:
            result["status"] = "❌ Cookie已失效（微信公众号API检测）"
    except Exception as e:
        result["error"] = str(e)[:200]
        result["status"] = f"⚠️ API检测异常: {str(e)[:80]}"
    return result


def _api_wordpress(cookie_str: str, site_url: str = "") -> dict:
    """WordPress API 级验证"""
    result = {"logged_in": False, "method": "api_lightweight",
              "platform": "wordpress", "site_url": site_url or "https://wordpress.com"}
    if not site_url:
        result["status"] = "⚠️ 需要 site_url 才能验证 WordPress"
        result["error"] = "site_url 不能为空"
        return result
    try:
        sess = _make_session()
        for name, value in _cookie_str_to_map(cookie_str).items():
            sess.cookies.set(name, value)
        # 尝试访问 WordPress REST API 用户端点
        site = site_url.rstrip("/")
        resp = sess.get(
            f"{site}/wp-json/wp/v2/users/me",
            timeout=10,
            allow_redirects=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            username = data.get("name", "") or data.get("slug", "")
            result["logged_in"] = True
            result["username"] = username
            result["display_name"] = data.get("name", "")
            result["verified_at"] = datetime.now().isoformat()
            result["status"] = f"✅ {username}（WordPress REST API）"
            return result
        # 回退：访问后台页面
        admin_resp = sess.get(f"{site}/wp-admin/", timeout=10, allow_redirects=True)
        if "wp-admin" in admin_resp.url and "login" not in admin_resp.url.lower():
            html = admin_resp.text
            m = re.search(r'howdy,\s*([^<]+)', html, re.IGNORECASE)
            extracted = m.group(1).strip() if m else ""
            uname = extracted
            result["logged_in"] = bool(uname)
            result["username"] = uname
            result["display_name"] = uname
            result["verified_at"] = datetime.now().isoformat()
            result["status"] = f"✅ {uname}（WordPress 后台）" if uname else "❌ Cookie已失效"
            return result
        result["status"] = "❌ Cookie已失效（WordPress）"
        result["error"] = "重定向到登录页"
    except Exception as e:
        result["error"] = str(e)[:200]
        result["status"] = f"⚠️ API检测异常: {str(e)[:80]}"
    return result


# ═══════════════════════════════════════════════════════════════
# 注册表
# ═══════════════════════════════════════════════════════════════

# 每个平台注册 = {keyword_handler, api_handler, requires_site_url, site_url_default}
PLATFORM_REGISTRY: dict[str, dict] = {
    "bilibili": {
        "keyword_handler": _keyword_bilibili,
        "api_handler": _api_bilibili,
        "requires_site_url": False,
        "site_url_default": "https://www.bilibili.com",
        "display_name": "B站",
    },
    "discuz": {
        "keyword_handler": _keyword_discuz,
        "api_handler": _api_discuz,
        "requires_site_url": True,
        "site_url_default": "",
        "display_name": "Discuz论坛",
    },
    "amobbs": {
        "keyword_handler": _keyword_amobbs,
        "api_handler": _api_amobbs,
        "requires_site_url": True,
        "site_url_default": "https://www.amobbs.com",
        "display_name": "阿莫论坛",
    },
    "wechat": {
        "keyword_handler": _keyword_wechat,
        "api_handler": _api_wechat,
        "requires_site_url": False,
        "site_url_default": "https://mp.weixin.qq.com",
        "display_name": "微信公众号",
    },
    "oshwhub": {
        "keyword_handler": _keyword_oshwhub,
        "api_handler": _api_oshwhub,
        "requires_site_url": False,
        "site_url_default": "https://oshwhub.com",
        "display_name": "立创开源硬件",
    },
    "csdn": {
        "keyword_handler": _keyword_csdn,
        "api_handler": _api_csdn,
        "requires_site_url": False,
        "site_url_default": "https://blog.csdn.net",
        "display_name": "CSDN",
    },
    "zhihu": {
        "keyword_handler": _keyword_zhihu,
        "api_handler": _api_zhihu,
        "requires_site_url": False,
        "site_url_default": "https://www.zhihu.com",
        "display_name": "知乎",
    },
    "juejin": {
        "keyword_handler": _keyword_juejin,
        "api_handler": _api_juejin,
        "requires_site_url": False,
        "site_url_default": "https://juejin.cn",
        "display_name": "掘金",
    },
    "xianyu": {
        "keyword_handler": _keyword_xianyu,
        "api_handler": _api_xianyu,
        "requires_site_url": False,
        "site_url_default": "https://goofish.com",
        "display_name": "闲鱼",
    },
    "wordpress": {
        "keyword_handler": _keyword_wordpress,
        "api_handler": _api_wordpress,
        "requires_site_url": True,
        "site_url_default": "",
        "display_name": "WordPress",
    },
}


def list_supported_platforms() -> list[dict]:
    """列出所有支持的平台及其注册信息"""
    return [
        {
            "platform": name,
            "display_name": info["display_name"],
            "requires_site_url": info["requires_site_url"],
            "site_url_default": info["site_url_default"],
        }
        for name, info in PLATFORM_REGISTRY.items()
    ]


# ═══════════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════════

def verify_cookie(
    platform: str,
    cookie_input: Any,
    input_type: str = "auto",
    site_url: str = "",
    username_hint: str = "",
    phase: str = "auto",
) -> dict:
    """
    统一 Cookie 验证入口 — 两阶段：关键字级 → API 级

    Args:
        platform: 平台名
            bilibili, discuz, amobbs, wechat, oshwhub, csdn,
            zhihu, juejin, xianyu, wordpress
        cookie_input: Cookie 输入
            - input_type='string': "; " 分隔的 Cookie 字符串
            - input_type='list': Playwright cookies() 返回的 list[dict]
        input_type: 输入类型
            'string' | 'list' | 'auto'（默认 auto，自动检测）
        site_url: 站点 URL
            discuz/amobbs 需要此参数指定论坛地址；wordpress 需要。
            其他平台可留空使用默认值。
        username_hint: 用户名提示
            仅 oshwhub 使用，辅助识别。
        phase: 验证阶段控制
            'keyword' — 仅关键字检查，无网络请求（适合 Playwright 轮询场景）
            'api'     — 跳过关键字，直接 API 验证
            'auto'    — 先关键字，再 API 确认；API 异常时回退关键字（默认）

    Returns:
        dict: {
            "valid": bool,         # True=有效 False=无效
            "method": str,         # "keyword" | "api" | "none"
            "message": str,        # 人类可读的结果说明
            "platform": str,       # 平台名
            "detail": dict,        # 验证详情（含 logged_in/username/points 等）
        }

    两阶段验证：
        Phase 1 (keyword): 检查 Cookie 键/值特征，无网络开销。
        Phase 2 (api):     发起 HTTP 请求访问平台 API 深度验证。
        如果 Phase 1 返回 True 且有 api_handler，则执行 Phase 2 确认。
        如果 Phase 1 返回 False，仍有 api_handler 时执行 Phase 2 兜底。
    """
    # ── 参数归一化 ─────────────────────────────────────────────
    if input_type == "auto":
        input_type = _detect_input_type(cookie_input)

    cookie_map = _normalize_to_map(cookie_input, input_type)
    cookie_str = _normalize_to_str(cookie_input, input_type)

    platform = platform.lower()

    # ── 平台注册查询 ──────────────────────────────────────────
    reg = PLATFORM_REGISTRY.get(platform)
    if not reg:
        return {
            "valid": False,
            "method": "none",
            "message": f"不支持的平台: {platform}",
            "platform": platform,
            "detail": {},
        }

    # 自动补齐 site_url
    if not site_url and reg.get("requires_site_url") and reg.get("site_url_default"):
        site_url = reg["site_url_default"]
    if not site_url and not reg.get("requires_site_url"):
        site_url = reg.get("site_url_default", "")

    # ── Phase 1: 关键字级检查 ────────────────────────────────
    kw_handler = reg.get("keyword_handler")
    kw_result = {"valid": False, "message": "无关键字检查"}

    if kw_handler and cookie_map:
        try:
            kw_result = kw_handler(cookie_map)
        except Exception as e:
            logger.warning("Cookie keyword check failed for %s: %s", platform, e)
            kw_result = {"valid": False, "message": f"关键字检查异常: {str(e)[:60]}"}

    # ── Phase 2: API 级检查 ──────────────────────────────────
    api_handler = reg.get("api_handler")
    api_result = None

    # 决定是否执行 Phase 2
    _do_api = False
    if phase == "api":
        _do_api = True  # 强制 API
    elif phase == "keyword":
        _do_api = False  # 强制跳过 API
    elif phase == "auto":
        # auto: 有 API handler 且满足条件时执行
        if api_handler:
            if reg.get("requires_site_url") and not site_url:
                pass  # 需要 site_url 但未提供，跳过 API
            else:
                _do_api = True

    if _do_api and cookie_str:
        try:
            if platform == "discuz":
                api_result = api_handler(cookie_str, site_url)
            elif platform == "amobbs":
                api_result = api_handler(cookie_str, site_url)
            elif platform == "oshwhub":
                api_result = api_handler(cookie_str, username_hint=username_hint)
            elif platform == "wordpress":
                api_result = api_handler(cookie_str, site_url=site_url)
            else:
                api_result = api_handler(cookie_str)
        except Exception as e:
            logger.warning("Cookie API check failed for %s: %s", platform, e)

    # ── 综合判断 ──────────────────────────────────────────────
    if api_result is not None:
        logged_in = api_result.get("logged_in", False)
        return {
            "valid": logged_in,
            "method": "api",
            "message": "有效" if logged_in else "Cookie 已失效",
            "platform": platform,
            "detail": api_result,
        }

    # 仅有关键字结果
    if kw_result["valid"]:
        return {
            "valid": True,
            "method": "keyword",
            "message": kw_result["message"],
            "platform": platform,
            "detail": {"logged_in": True, "keyword_passed": True},
        }

    return {
        "valid": False,
        "method": "none",
        "message": kw_result.get("message", "Cookie 无效"),
        "platform": platform,
        "detail": {"logged_in": False, "keyword_passed": False},
    }


# ═══════════════════════════════════════════════════════════════
# Adapter 兼容接口
# ═══════════════════════════════════════════════════════════════

def has_valid_cookie(
    platform: str,
    cookie_input: Any,
    input_type: str = "auto",
    site_url: str = "",
    username_hint: str = "",
    phase: str = "auto",
) -> bool:
    """
    简化的布尔接口 — 仅返回 Cookie 是否有效

    等同于 verify_cookie(...)["valid"]，适用于 Adapter 的
    test_connection() / _has_valid_cookie() 等快速调用的场景。
    """
    result = verify_cookie(platform, cookie_input, input_type, site_url, username_hint, phase)
    return result["valid"]


def verify_cookie_for_adapter(
    platform: str,
    config: dict,
    cookie_key: str = "cookie",
) -> dict:
    """
    Adapter 专用便捷接口 — 直接从 config 中提取 Cookie 验证

    用于 sdk/adapters/*.py 的 test_connection() 统一替换。

    Args:
        platform: 平台名
        config: Adapter 的 config 字典
        cookie_key: config 中存储 Cookie 的键名，默认 "cookie"

    Returns:
        同 verify_cookie() 的返回值
    """
    cookie_str = (config or {}).get(cookie_key, "")
    site_url = (config or {}).get("site_url", "")
    username = (config or {}).get("username", "")
    return verify_cookie(
        platform=platform,
        cookie_input=cookie_str,
        input_type="string",
        site_url=site_url,
        username_hint=username,
    )
