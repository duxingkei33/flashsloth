"""FlashSloth 常驻 Playwright 浏览器引擎 — 全局单例

核心职责：
  1. 管理一个持久化 Playwright Browser 进程（不反复 launch/close）
  2. 提供线程安全的 get_page() / close_tab() 接口
  3. 10 分钟无活动自动关闭（省资源）
  4. 状态变化实时可查（供前端状态栏消费）

使用方法：
    from flashsloth.core.browser_engine import BrowserEngine
    engine = BrowserEngine.get_instance()
    page = engine.get_page()          # 获取可用页面
    # ... 做操作 ...
    engine.close_tab(page)            # 操作完关闭标签页
"""

from __future__ import annotations

import json
import os
import random
import time
import threading
import datetime
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─── 默认配置 ───
PLAYWRIGHT_DEFAULT_CONFIG = {
    "browser_type": "chromium",         # chromium | firefox | webkit
    "headless": True,
    "viewport_width": 1280,
    "viewport_height": 800,
    "user_agent": "",
    "timeout": 30000,                    # 默认超时30秒
    "navigation_timeout": 30000,
    "locale": "zh-CN",
    "proxy": "",                         # 代理地址
    "data_dir": "",                      # 持久化用户数据目录
    "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
    "auto_start": True,                  # 登录后自动启动
    "auto_close_minutes": 10,            # 无活动自动关闭时间
}

# 状态常量
STATUS_STOPPED = "stopped"
STATUS_STARTING = "starting"
STATUS_READY = "ready"
STATUS_RESTARTING = "restarting"
STATUS_ERROR = "error"

_BADGE_MAP = {
    STATUS_STARTING: ("badge-warning", "🖥️ 启动中"),
    STATUS_READY: ("badge-success", "🖥️ 已就绪"),
    STATUS_RESTARTING: ("badge-warning", "🖥️ 重启中"),
    STATUS_ERROR: ("badge-danger", "🖥️ 异常"),
    STATUS_STOPPED: ("badge-secondary", "🖥️ 已停止"),
}


class BrowserEngine:
    """常驻 Playwright 浏览器管理器 — 全局单例"""

    _instance = None
    _instance_lock = threading.Lock()

    _browser = None
    _context = None
    _playwright = None
    _status = STATUS_STOPPED
    _last_activity = 0.0
    _start_time = 0.0
    _lock = threading.Lock()
    _config = dict(PLAYWRIGHT_DEFAULT_CONFIG)
    _error_msg = ""

    # ── 单例 ──────────────────────────────────

    @classmethod
    def get_instance(cls) -> "BrowserEngine":
        """获取或创建单例"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._config = dict(PLAYWRIGHT_DEFAULT_CONFIG)
        self._lock = threading.Lock()
        self._browser = None
        self._context = None
        self._playwright = None
        self._status = STATUS_STOPPED
        self._last_activity = 0.0
        self._start_time = 0.0
        self._error_msg = ""

    # ── 配置管理 ──────────────────────────────

    def load_config_from_db(self):
        """从数据库加载 Playwright 配置（覆盖默认值）"""
        try:
            from flashsloth.core.database import get_db
            conn = get_db()
            row = conn.execute(
                "SELECT config_json FROM playwright_config WHERE id=1"
            ).fetchone()
            conn.close()
            if row and row["config_json"]:
                cfg = json.loads(row["config_json"])
                self._config.update(cfg)
                logger.info("BrowserEngine: loaded config from DB")
        except Exception as e:
            logger.warning(f"BrowserEngine: failed to load config from DB: {e}")

    def save_config_to_db(self) -> bool:
        """保存当前配置到数据库"""
        try:
            from flashsloth.core.database import get_db
            conn = get_db()
            conn.execute(
                "INSERT OR REPLACE INTO playwright_config (id, config_json) VALUES (1, ?)",
                (json.dumps(self._config, ensure_ascii=False),),
            )
            conn.commit()
            conn.close()
            logger.info("BrowserEngine: config saved to DB")
            return True
        except Exception as e:
            logger.error(f"BrowserEngine: failed to save config: {e}")
            return False

    def update_config(self, updates: dict) -> dict:
        """更新配置项并返回完整配置"""
        with self._lock:
            for k, v in updates.items():
                if k in self._config:
                    # 特殊处理 args 字段（逗号分隔→列表）
                    if k == "args" and isinstance(v, str):
                        self._config[k] = [a.strip() for a in v.split(",") if a.strip()]
                    else:
                        self._config[k] = v
            self.save_config_to_db()
            return dict(self._config)

    def get_config(self) -> dict:
        """获取当前配置副本"""
        with self._lock:
            return dict(self._config)

    # ── 生命周期管理 ──────────────────────────

    def start(self) -> bool:
        """启动 Playwright 浏览器（配置从 DB/默认读取）"""
        with self._lock:
            if self._status == STATUS_READY:
                logger.info("BrowserEngine: already running")
                return True
            if self._status == STATUS_STARTING:
                logger.warning("BrowserEngine: already starting")
                return False
            self._status = STATUS_STARTING
            self._error_msg = ""

        try:
            self.load_config_from_db()
            cfg = self._config

            from playwright.sync_api import sync_playwright

            pw = sync_playwright().start()
            launch_kwargs = {
                "headless": cfg.get("headless", True),
                "args": cfg.get("args", ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]),
                "timeout": cfg.get("timeout", 30000),
            }

            # 代理
            proxy = cfg.get("proxy", "").strip()
            if proxy:
                launch_kwargs["proxy"] = {"server": proxy}

            # 数据目录（持久化）
            data_dir = cfg.get("data_dir", "").strip()
            if data_dir:
                os.makedirs(data_dir, exist_ok=True)
                launch_kwargs["user_data_dir"] = data_dir

            browser_type_name = cfg.get("browser_type", "chromium")
            browser_type = getattr(pw, browser_type_name, pw.chromium)
            browser = browser_type.launch(**launch_kwargs)

            # 创建上下文
            context_kwargs = {
                "viewport": {
                    "width": cfg.get("viewport_width", 1280),
                    "height": cfg.get("viewport_height", 800),
                },
                "locale": cfg.get("locale", "zh-CN"),
            }

            ua = cfg.get("user_agent", "").strip()
            if ua:
                context_kwargs["user_agent"] = ua

            # 注入反检测脚本
            context = browser.new_context(**context_kwargs)
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en']
                });
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
            """)

            # 默认打开一个空白页面
            page = context.new_page()
            page.goto("about:blank")

            with self._lock:
                self._playwright = pw
                self._browser = browser
                self._context = context
                self._status = STATUS_READY
                self._last_activity = time.time()
                self._start_time = time.time()
                self._error_msg = ""

            logger.info(f"BrowserEngine: {browser_type_name} started (headless={cfg.get('headless')})")
            return True

        except Exception as e:
            err = str(e)
            logger.error(f"BrowserEngine: failed to start: {err}")
            with self._lock:
                self._status = STATUS_ERROR
                self._error_msg = err
            return False

    def stop(self) -> bool:
        """停止浏览器，关闭所有页面和上下文"""
        with self._lock:
            old_status = self._status
            self._status = STATUS_STOPPED
            self._error_msg = ""

        try:
            if self._context:
                try:
                    self._context.close()
                except Exception:
                    pass
                self._context = None

            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

            logger.info("BrowserEngine: stopped")
            return True
        except Exception as e:
            logger.error(f"BrowserEngine: stop error: {e}")
            return False

    def restart(self) -> bool:
        """重启浏览器"""
        logger.info("BrowserEngine: restarting...")
        with self._lock:
            self._status = STATUS_RESTARTING

        self.stop()
        time.sleep(0.5)
        return self.start()

    # ── 页面管理 ──────────────────────────────

    def get_page(self) -> object:
        """获取当前活跃页面（如无则新建一个）"""
        with self._lock:
            if self._status != STATUS_READY or not self._browser:
                self._lock.release()
                # 自动尝试启动
                ok = self.start()
                if not ok:
                    raise RuntimeError(
                        f"BrowserEngine not ready (status={self._status})"
                    )
                return self.get_page()

            # 标记活动时间
            self._last_activity = time.time()

            # 找一个可用的页面（非空白页考虑复用）
            pages = self._context.pages if self._context else []

            for p in pages:
                try:
                    url = p.url
                    if url in ("about:blank", ""):
                        return p
                except Exception:
                    continue

            # 没有可用页面 → 新建
            page = self._context.new_page()
            return page

    def close_tab(self, page):
        """关闭指定标签页，确保至少保留 1 个空白页"""
        if not page:
            return
        try:
            page.close()
        except Exception:
            pass

        with self._lock:
            self._last_activity = time.time()

            # 确保至少有一个空白页
            if self._context:
                try:
                    pages = self._context.pages
                    if not pages:
                        p = self._context.new_page()
                        p.goto("about:blank")
                except Exception:
                    pass

    def keep_alive(self):
        """标记活动时间（每次操作时调用）"""
        with self._lock:
            self._last_activity = time.time()

    # ── 状态查询 ──────────────────────────────

    def get_status(self) -> dict:
        """返回状态信息"""
        with self._lock:
            status = self._status
            tabs_count = 0
            pid = None
            memory_mb = None

            if self._context:
                try:
                    tabs_count = len(self._context.pages)
                except Exception:
                    pass

            uptime = 0.0
            if self._start_time > 0:
                uptime = time.time() - self._start_time

            badge_cls, badge_text = _BADGE_MAP.get(status, ("badge-secondary", "🖥️ 未知"))

            return {
                "status": status,
                "badge_class": badge_cls,
                "badge_text": badge_text,
                "tabs_count": tabs_count,
                "uptime": round(uptime, 1),
                "uptime_str": self._format_uptime(uptime),
                "error": self._error_msg,
                "pid": pid,
                "memory_mb": memory_mb,
                "last_activity_ago": round(time.time() - self._last_activity, 1)
                    if self._last_activity > 0 else 0,
                "config": self.get_config(),
            }

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """格式化运行时长"""
        if seconds <= 0:
            return "0秒"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        parts = []
        if h:
            parts.append(f"{h}小时")
        if m:
            parts.append(f"{m}分")
        if s or not parts:
            parts.append(f"{s}秒")
        return "".join(parts)

    def check_activity_timeout(self):
        """检查是否超过配置时间无活动 → 自动关闭"""
        cfg_auto_close = self._config.get("auto_close_minutes", 10)

        # 0 或负数表示不自动关闭
        if cfg_auto_close <= 0:
            return

        with self._lock:
            if self._status != STATUS_READY:
                return
            elapsed = time.time() - self._last_activity
            if elapsed >= cfg_auto_close * 60:
                logger.info(
                    f"BrowserEngine: auto-closing after {cfg_auto_close}min inactivity "
                    f"({elapsed:.0f}s elapsed)"
                )
                self._lock.release()
                self.stop()
                return

    def is_ready(self) -> bool:
        """快捷检查引擎是否就绪"""
        with self._lock:
            return self._status == STATUS_READY and self._browser is not None


# ─── 全局便捷函数 ─────────────────────────────

def get_engine() -> BrowserEngine:
    """快捷获取单例"""
    return BrowserEngine.get_instance()


def get_engine_status() -> dict:
    """快捷获取状态"""
    return get_engine().get_status()


def start_engine() -> bool:
    """快捷启动"""
    return get_engine().start()


def stop_engine() -> bool:
    """快捷停止"""
    return get_engine().stop()
