"""闲鱼 MTOP API 客户端 — 移植自 goofish-cli

基于 MTOP 签名 API 实现的闲鱼自动化客户端，支持：
- Cookie 导入（浏览器自动探测 / 文件 / 字符串）
- QR 扫码登录兜底
- Playwright 自动刷新 session
- MTOP 签名 API 调用（发布 / 图片上传 / 类目识别 / 地址获取）
- 令牌桶限流 + 风控熔断
"""
from .sign import generate_sign, generate_device_id, generate_mid, generate_uuid
from .errors import (
    AuthRequiredError, SignError, RateLimitedError,
    RiskControlError, NotFoundError, EmptyResultError, BlockedError,
)
from .session import Session, resolve_cookie_path, write_cookies_json
from .mtop import call as mtop_call, APP_KEY, MTOP_HOST
from .guard import check as guard_check, trip as guard_trip, reset as guard_reset
from .limiter import acquire as limiter_acquire, check as limiter_check

__all__ = [
    "generate_sign", "generate_device_id", "generate_mid", "generate_uuid",
    "AuthRequiredError", "SignError", "RateLimitedError",
    "RiskControlError", "NotFoundError", "EmptyResultError", "BlockedError",
    "Session", "resolve_cookie_path", "write_cookies_json",
    "mtop_call", "APP_KEY", "MTOP_HOST",
    "guard_check", "guard_trip", "guard_reset",
    "limiter_acquire", "limiter_check",
]
