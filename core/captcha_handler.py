"""
Captcha Handler — 通用验证码处理服务

功能：
  1. 发布前检查登录状态，失效则自动触发登录
  2. 验证码弹窗：后台API返回base64图片，用户在前端输入
  3. 多轮验证码：支持 2~3 次连续验证码（如amobbs）
  4. 预留自动接码平台接口（2captcha, ttshitu）
  5. 与 PlatformAdapter 无缝集成

流程：
  发布时 → check_login() → 失效 →
    login() → 有验证码? → 存captchaChallenge → 通知前端弹窗 →
    用户输入 → submit_captcha() → 再验证 → 直到成功或达到最大次数 →
    成功 → 发帖
"""
import json, time, base64, re, os
from typing import Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


# ═══════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════

class CaptchaProvider(str, Enum):
    """验证码处理方式"""
    MANUAL = "manual"           # 手动输入（弹窗）
    AUTO_TTSHITU = "ttshitu"    # 自动识别-图鉴
    AUTO_2CAPTCHA = "2captcha"  # 自动识别-2captcha
    AUTO_CUSTOM = "custom"      # 自定义API


@dataclass
class CaptchaChallenge:
    """一次验证码挑战"""
    id: str                        # 唯一标识
    platform: str                  # 平台名（如 discuz, amobbs）
    account_id: int                # 账号ID
    site_url: str                  # 网站地址
    image_base64: str              # 验证码图片（base64）
    image_mime: str = "image/png"  # 图片MIME类型
    attempt: int = 1               # 第几次验证码（1-based）
    max_attempts: int = 3          # 最大尝试次数
    seccodehash: str = ""          # Discuz! 等平台的验证码hash
    extra: dict = field(default_factory=dict)  # 平台额外参数
    status: str = "pending"        # pending / submitted / success / failed
    error: str = ""                # 错误信息
    created_at: str = ""           # 创建时间


@dataclass
class CaptchaProviderConfig:
    """验证码提供商配置"""
    provider: CaptchaProvider = CaptchaProvider.MANUAL
    api_key: str = ""
    api_url: str = ""
    # ttshitu 专用
    ttshitu_username: str = ""
    ttshitu_password: str = ""
    # 2captcha 专用
    two_captcha_key: str = ""


# ═══════════════════════════════════════════════
# 验证码处理服务
# ═══════════════════════════════════════════════

class CaptchaHandler:
    """
    验证码处理服务 — 管理所有平台的验证码挑战。

    工作流：
      1. start_login(platform, account_id) → 返回 CaptchaChallenge（含base64图片）
      2. 前端显示图片让用户输入 → submit_captcha(challenge_id, code)
      3. 系统尝试登录 → 如果又出验证码 → repeat(2) 最多 max_attempts 次
      4. 成功 → 返回登录凭证（cookie/token）
      5. 失败 → 返回错误信息
    """

    def __init__(self, db_path: str = ""):
        self._db_path = db_path or os.environ.get(
            "FLASHSLOTH_DB",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db"),
        )
        self._challenges: dict[str, CaptchaChallenge] = {}
        self._provider_configs: dict[int, CaptchaProviderConfig] = {}  # account_id → config

    # ─── 数据库 ─────────────────────────────────

    def _get_db(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ─── 配置管理 ───────────────────────────────

    def get_provider_config(self, account_id: int) -> CaptchaProviderConfig:
        """获取账号的验证码处理配置"""
        if account_id in self._provider_configs:
            return self._provider_configs[account_id]

        conn = self._get_db()
        row = conn.execute(
            "SELECT captcha_provider, captcha_config FROM platform_accounts WHERE id=?",
            (account_id,),
        ).fetchone()
        conn.close()

        if row and row["captcha_provider"]:
            cfg = json.loads(row["captcha_config"]) if row["captcha_config"] else {}
            provider = CaptchaProvider(row["captcha_provider"])
            pcfg = CaptchaProviderConfig(provider=provider, **cfg)
        else:
            pcfg = CaptchaProviderConfig()

        self._provider_configs[account_id] = pcfg
        return pcfg

    def update_provider_config(
        self, account_id: int, provider: str, config: dict
    ) -> bool:
        """更新账号的验证码处理配置"""
        conn = self._get_db()
        conn.execute(
            "UPDATE platform_accounts SET captcha_provider=?, captcha_config=? WHERE id=?",
            (provider, json.dumps(config), account_id),
        )
        conn.commit()
        conn.close()
        self._provider_configs.pop(account_id, None)
        return True

    # ─── 验证码挑战管理 ──────────────────────────

    def create_challenge(
        self,
        platform: str,
        account_id: int,
        site_url: str,
        image_base64: str,
        image_mime: str = "image/png",
        seccodehash: str = "",
        attempt: int = 1,
        max_attempts: int = 3,
        extra: dict = None,
    ) -> CaptchaChallenge:
        """创建验证码挑战"""
        challenge_id = f"captcha_{int(time.time())}_{account_id}_{attempt}"
        challenge = CaptchaChallenge(
            id=challenge_id,
            platform=platform,
            account_id=account_id,
            site_url=site_url,
            image_base64=image_base64,
            image_mime=image_mime,
            seccodehash=seccodehash,
            attempt=attempt,
            max_attempts=max_attempts,
            extra=extra or {},
            created_at=datetime.now().isoformat(),
        )
        self._challenges[challenge_id] = challenge
        return challenge

    def get_challenge(self, challenge_id: str) -> Optional[CaptchaChallenge]:
        """获取验证码挑战"""
        return self._challenges.get(challenge_id)

    def remove_challenge(self, challenge_id: str):
        """移除已处理的挑战"""
        self._challenges.pop(challenge_id, None)

    def has_pending_challenge(self, account_id: int) -> bool:
        """检查账号是否有待处理的验证码挑战"""
        for c in self._challenges.values():
            if c.account_id == account_id and c.status == "pending":
                return True
        return False

    # ─── 核心流程 ───────────────────────────────

    def start_login(self, platform: str, account_id: int, config: dict) -> dict:
        """
        启动登录流程。
        
        如果有验证码 → 返回 challenge（含base64图片）
        如果不需要验证码 → 直接登录并返回session
        
        返回: {
            "success": bool,
            "challenge_id": str,      # 如果有验证码
            "image": str,             # base64图片（有验证码时）
            "seccodehash": str,       # 验证码hash
            "session_data": dict,     # 登录成功后的session
            "error": str,
        }
        """
        raise NotImplementedError("由具体平台适配器实现")

    def submit_captcha(self, challenge_id: str, captcha_code: str) -> dict:
        """
        提交验证码，继续登录流程。

        内部调用适配器的 login_with_captcha()。
        如果又出现验证码 → 返回新的 challenge（最多 max_attempts 次）
        如果成功 → 返回登录凭证
        
        返回: {
            "success": bool,
            "logged_in": bool,         # 是否最终登录成功
            "challenge_id": str,       # 原challenge
            "new_challenge": dict,     # 如果又出现新验证码
            "session_data": dict,      # 登录凭证
            "attempt": int,            # 当前第几次
            "max_attempts": int,
            "error": str,
        }
        """
        challenge = self.get_challenge(challenge_id)
        if not challenge:
            return {"success": False, "error": "验证码挑战已过期，请重新获取"}

        if challenge.attempt > challenge.max_attempts:
            challenge.status = "failed"
            return {
                "success": False,
                "error": f"验证码已超过最大尝试次数（{challenge.max_attempts}次）",
                "attempt": challenge.attempt,
                "max_attempts": challenge.max_attempts,
            }

        # 尝试提交（由具体的LoginCallback实现）
        try:
            result = self._try_login_with_code(challenge, captcha_code)
        except Exception as e:
            challenge.status = "failed"
            challenge.error = str(e)
            return {
                "success": False,
                "error": f"登录异常: {e}",
                "attempt": challenge.attempt,
                "max_attempts": challenge.max_attempts,
            }

        if result.get("success"):
            challenge.status = "success"
            self.remove_challenge(challenge_id)
            return {
                "success": True,
                "logged_in": True,
                "challenge_id": challenge_id,
                "session_data": result.get("session_data"),
                "attempt": challenge.attempt,
                "max_attempts": challenge.max_attempts,
            }

        # 检查是否出现了新的验证码
        new_captcha = result.get("new_captcha")
        if new_captcha:
            next_attempt = challenge.attempt + 1
            if next_attempt > challenge.max_attempts:
                challenge.status = "failed"
                return {
                    "success": False,
                    "error": f"验证码已超过最大尝试次数（{challenge.max_attempts}次）",
                    "attempt": challenge.attempt,
                    "max_attempts": challenge.max_attempts,
                }

            # 创建新的验证码挑战
            new_challenge = self.create_challenge(
                platform=challenge.platform,
                account_id=challenge.account_id,
                site_url=challenge.site_url,
                image_base64=new_captcha.get("image_base64", ""),
                image_mime=new_captcha.get("image_mime", "image/png"),
                seccodehash=new_captcha.get("seccodehash", ""),
                attempt=next_attempt,
                max_attempts=challenge.max_attempts,
                extra=new_captcha.get("extra"),
            )

            challenge.status = "submitted"
            return {
                "success": True,
                "logged_in": False,
                "challenge_id": challenge_id,
                "new_challenge": {
                    "id": new_challenge.id,
                    "image": f"data:{new_challenge.image_mime};base64,{new_challenge.image_base64}",
                    "seccodehash": new_challenge.seccodehash,
                    "attempt": next_attempt,
                    "max_attempts": challenge.max_attempts,
                    "error": result.get("error", "验证码错误，请重新输入"),
                },
                "error": result.get("error", "验证码错误，请重新输入"),
                "attempt": challenge.attempt,
                "max_attempts": challenge.max_attempts,
            }

        # 普通失败
        challenge.status = "failed"
        challenge.error = result.get("error", "登录失败")
        return {
            "success": False,
            "error": result.get("error", "登录失败"),
            "attempt": challenge.attempt,
            "max_attempts": challenge.max_attempts,
        }

    def _try_login_with_code(self, challenge: CaptchaChallenge, code: str) -> dict:
        """
        用验证码尝试登录。
        子类覆盖此方法或使用 set_login_callback()。
        """
        if self._login_callback:
            return self._login_callback(challenge, code)
        return {"success": False, "error": "未设置登录回调函数"}

    _login_callback: Optional[Callable] = None

    def set_login_callback(self, callback: Callable):
        """
        设置验证码登录回调函数。
        
        回调签名:
            def callback(challenge: CaptchaChallenge, code: str) -> dict:
                返回:
                    {"success": True, "session_data": {...}}  # 登录成功
                    {"success": False, "error": "..."}         # 登录失败
                    {"success": False, "new_captcha": {...}}   # 又有新验证码
        """
        self._login_callback = callback

    # ─── 自动接码（预留） ──────────────────────────

    def auto_solve(self, image_base64: str, provider: CaptchaProvider) -> Optional[str]:
        """
        使用自动接码平台识别验证码。
        
        预留接口，目前返回 None（需要配置API密钥）。
        支持的平台: ttshitu (图鉴), 2captcha
        """
        if provider == CaptchaProvider.AUTO_TTSHITU:
            return self._solve_ttshitu(image_base64)
        elif provider == CaptchaProvider.AUTO_2CAPTCHA:
            return self._solve_2captcha(image_base64)
        return None

    def _solve_ttshitu(self, image_base64: str) -> Optional[str]:
        """图鉴自动识别（预留）"""
        # TODO: 实现 ttshitu API 调用
        # POST https://api.ttshitu.com/predict
        # {"username": "...", "password": "...", "image": image_base64, "typeid": 1}
        return None

    def _solve_2captcha(self, image_base64: str) -> Optional[str]:
        """2captcha 自动识别（预留）"""
        # TODO: 实现 2captcha API 调用
        return None


# ═══════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════

_handler: Optional[CaptchaHandler] = None


def get_handler() -> CaptchaHandler:
    """获取全局 CaptchaHandler 实例"""
    global _handler
    if _handler is None:
        _handler = CaptchaHandler()
    return _handler


def init_handler(db_path: str = ""):
    """初始化全局 CaptchaHandler"""
    global _handler
    _handler = CaptchaHandler(db_path)
