"""FlashSloth — 账号管理路由：共享工具函数"""
import json
import os
import threading

# ─── 引擎类型（数据驱动 — 从探索JSON的 engine 字段推导，铁律#19）───
_ENGINE_FALLBACK_MAP = {
    "amobbs": "discuz", "discuz": "discuz", "mydigit": "discuz",
    "xianyu": "xianyu", "xianyu_v2": "xianyu",
    "oshwhub": "oshwhub",
    "csdn": "generic", "wechat": "generic", "bilibili": "generic",
    "juejin": "generic", "zhihu": "generic", "wordpress": "generic",
}

# 平台名 → JSON文件名 映射（处理名称不一致）
_PLATFORM_CAP_MAP = {
    "wechat": "wechat_mp",
    "xianyu_v2": "xianyu",
    "xianyu_sidecar": "xianyu",
    "xianyu_auto_reply": "xianyu",
    "xianyu_products": "xianyu",
}

_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "platform_reports")

# OAuth provider 图标映射
_OAUTH_ICON_MAP = {
    "qq": "🐧",
    "weibo": "📣",
    "wechat_oauth": "💬",
    "github": "🐙",
    "google": "🔵",
    "apple": "🍎",
}

# OAuth provider 标签映射
_OAUTH_LABEL_MAP = {
    "qq": "QQ登录",
    "weibo": "微博登录",
    "wechat_oauth": "微信登录",
    "github": "GitHub登录",
    "google": "Google登录",
    "apple": "Apple登录",
}

_login_locks: dict[str, threading.Lock] = {}


def _get_login_lock(platform: str) -> threading.Lock:
    """获取平台锁"""
    if platform not in _login_locks:
        _login_locks[platform] = threading.Lock()
    return _login_locks[platform]


def _infer_config_fields_from_cap(cap: dict) -> list:
    """从探索数据推导配置字段列表"""
    fields = set()
    methods = cap.get("login_methods", [])
    login_url = cap.get("login_url", "")
    engine = cap.get("engine", "")

    # Discuz 类平台需要 site_url（相对路径 login_url）
    if engine == "discuz" or "discuz" in (cap.get("note") or "").lower():
        fields.add("site_url")

    # 登录 URL 是相对路径 → 需要 site_url
    if login_url and not login_url.startswith("http"):
        fields.add("site_url")

    # 从登录方法推导
    for m in methods:
        method = m.get("method", "")
        if method == "password":
            fields.add("username")
            fields.add("password")
        elif method == "qrcode":
            # QR码不需要额外字段（系统自动打开扫码页）
            pass
        elif method == "oauth":
            pass
        elif method == "phone":
            fields.add("phone")
        elif method == "cookie":
            pass

    # 默认至少需要 site_url
    if not fields:
        fields.add("site_url")

    return sorted(fields)


def _get_engine_for_platform(platform: str) -> str:
    """从探索数据推导登录引擎，无数据则回退到映射表"""
    cap = _load_login_capabilities(platform)
    engine = cap.get("engine") if cap else None
    return engine if engine else _ENGINE_FALLBACK_MAP.get(platform, "unknown")


def _load_login_capabilities(platform: str) -> dict | None:
    """从 platform_reports 加载指定平台的登录能力数据"""
    json_name = _PLATFORM_CAP_MAP.get(platform, platform)
    report_path = os.path.join(_REPORTS_DIR, f"{json_name}_login_capabilities.json")
    if os.path.exists(report_path):
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _extract_captcha_info(raw_detection: dict | None) -> dict:
    """从 raw_detection 中提取验证码信息"""
    if not raw_detection:
        return {"has_captcha": False, "types": [], "note": ""}
    has_captcha = raw_detection.get("has_captcha", False)
    captcha_type = raw_detection.get("captcha_type")
    captcha_note = raw_detection.get("captcha_description") or raw_detection.get("captcha_note") or ""
    return {
        "has_captcha": bool(has_captcha),
        "types": [captcha_type] if captcha_type else [],
        "note": captcha_note,
    }


def _enhance_login_methods(methods: list, raw_detection: dict | None) -> list:
    """增强登录方法列表：添加 fields、展开 providers、添加 captcha 信息"""
    enhanced = []
    captcha_info = _extract_captcha_info(raw_detection)
    for m in methods:
        if not m.get("detected"):
            continue
        method = m["method"]
        entry = dict(m)  # shallow copy to preserve original fields
        if method == "password":
            entry["fields"] = ["username", "password"]
            entry["captcha"] = {
                "has_captcha": captcha_info["has_captcha"],
                "type": captcha_info["types"][0] if captcha_info["types"] else None,
                "description": captcha_info["note"] or None,
            }
        elif method == "phone":
            entry["fields"] = ["phone"]
        elif method == "qrcode":
            # 保留原有的 sub_types 数组
            pass
        elif method == "oauth":
            providers = m.get("providers", [])
            entry["providers"] = [
                {
                    "id": pid,
                    "label": _OAUTH_LABEL_MAP.get(pid, f"{pid}登录"),
                    "icon": _OAUTH_ICON_MAP.get(pid, "🔗"),
                }
                for pid in providers
            ]
        elif method == "cookie":
            entry["fields"] = ["cookie"]
        enhanced.append(entry)
    return enhanced
