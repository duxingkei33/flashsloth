"""统一异常体系 — 移植自 goofish-cli"""
from __future__ import annotations


class GoofishError(Exception):
    exit_code = 1

    def __init__(self, message: str, *, raw: dict | None = None, hint: str | None = None):
        super().__init__(message)
        self.raw = raw
        self.hint = hint


class AuthRequiredError(GoofishError):
    """登录态失效"""
    exit_code = 77


class SignError(GoofishError):
    """签名错误"""
    exit_code = 78


class RateLimitedError(GoofishError):
    """限流"""
    exit_code = 75


class RiskControlError(GoofishError):
    """触发风控：RGV587 / punish / FAIL_SYS_USER_VALIDATE"""
    exit_code = 76


class NotFoundError(GoofishError):
    """未找到"""
    exit_code = 79


class EmptyResultError(GoofishError):
    """查询无命中"""
    exit_code = 79


class BlockedError(GoofishError):
    """请求被拦截（验证码页 / 安全验证 / 异常访问）"""
    exit_code = 79
