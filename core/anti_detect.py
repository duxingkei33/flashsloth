"""FlashSloth — 反检测/防风共享中间件

核心原则：像真人一样操作，不触发平台反爬机制。
适用于所有Playwright交互（登录、发布、浏览、探索）。
移植自开源闲鱼Agent的防风措施 + 通用化。

使用方法:
    from flashsloth.core.anti_detect import create_human_context
    ctx = create_human_context(browser)
    page = ctx.new_page()
    # 然后使用 human_click, human_type 等替代原生方法
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Optional

# ══════════════════════════════════════════════════
# 可配置参数（可通过环境变量覆盖）
# ══════════════════════════════════════════════════

class AntiDetectConfig:
    """全局防风配置"""
    
    # 鼠标：每次移动的像素范围（随机）
    MOUSE_MIN_MOVE: int = int(os.environ.get("AD_MOUSE_MIN", "3"))
    MOUSE_MAX_MOVE: int = int(os.environ.get("AD_MOUSE_MAX", "50"))
    
    # 鼠标：移动间隔毫秒
    MOUSE_MIN_DELAY_MS: int = int(os.environ.get("AD_MOUSE_DELAY_MIN", "30"))
    MOUSE_MAX_DELAY_MS: int = int(os.environ.get("AD_MOUSE_DELAY_MAX", "120"))
    
    # 键盘：打字间隔毫秒
    TYPE_MIN_DELAY_MS: int = int(os.environ.get("AD_TYPE_DELAY_MIN", "50"))
    TYPE_MAX_DELAY_MS: int = int(os.environ.get("AD_TYPE_DELAY_MAX", "200"))
    
    # 操作间的最小/最大等待秒数
    OP_MIN_WAIT: float = float(os.environ.get("AD_OP_WAIT_MIN", "1.5"))
    OP_MAX_WAIT: float = float(os.environ.get("AD_OP_WAIT_MAX", "4.0"))
    
    # 页面滚动
    SCROLL_MIN_PX: int = int(os.environ.get("AD_SCROLL_MIN", "100"))
    SCROLL_MAX_PX: int = int(os.environ.get("AD_SCROLL_MAX", "600"))
    
    # Viewport 配置（随机选择）
    VIEWPORTS: list[dict] = [
        {"width": 1920, "height": 1080},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1366, "height": 768},
        {"width": 1280, "height": 800},
    ]
    
    # UA 列表（随机选择）
    USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    ]

    # 浏览器语言
    LOCALES: list[str] = ["zh-CN", "zh", "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"]

    # 时间偏移（时区）
    TIMEZONE_ID: str = "Asia/Shanghai"


# ══════════════════════════════════════════════════
# 浏览器上下文工厂
# ══════════════════════════════════════════════════

def create_human_context(
    browser,
    *,
    user_agent: Optional[str] = None,
    viewport: Optional[dict] = None,
    locale: Optional[str] = None,
    storage_state: Optional[dict] = None,
    **kwargs,
):
    """创建模拟真人的 browser context
    
    用法:
        ctx = create_human_context(browser)
        page = ctx.new_page()
    """
    cfg = AntiDetectConfig
    
    # 随机选UA
    ua = user_agent or random.choice(cfg.USER_AGENTS)
    # 随机选viewport
    vp = viewport or random.choice(cfg.VIEWPORTS)
    # 随机选locale
    loc = locale or random.choice(cfg.LOCALES)
    
    ctx = browser.new_context(
        user_agent=ua,
        viewport=vp,
        locale=loc,
        timezone_id=cfg.TIMEZONE_ID,
        # 屏蔽部分自动化特征
        permissions=["geolocation"],
        **kwargs,
    )
    
    # 注入反检测脚本（移除webdriver特征 + 篡改navigator）
    ctx.add_init_script("""
        // === 反检测：隐藏自动化特征 ===
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        
        // 伪装 plugins 长度（真实浏览器 > 3）
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // 伪装 languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en']
        });
        
        // 覆盖 chrome runtime
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // 覆盖 Permissions（防止检测到没有权限）
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' 
                ? Promise.resolve({state: Notification.permission})
                : originalQuery(parameters)
        );
        
        // 覆盖 WebGL vendor（防止 fingerprint）
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';
            if (p === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter(p);
        };
        
        // 覆盖头发送回显
        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
        
        // 覆盖屏幕深度
        Object.defineProperty(screen, 'colorDepth', {get: () => 24});
        Object.defineProperty(screen, 'pixelDepth', {get: () => 24});
    """)
    
    # 恢复存储状态（如果有）
    if storage_state:
        try:
            ctx.add_cookies(storage_state.get("cookies", []))
        except Exception:
            pass
    
    return ctx


# ══════════════════════════════════════════════════
# 人类行为模拟工具
# ══════════════════════════════════════════════════

def human_delay(min_sec: float = None, max_sec: float = None):
    """模拟人类操作的随机延迟"""
    cfg = AntiDetectConfig
    mn = min_sec if min_sec is not None else cfg.OP_MIN_WAIT
    mx = max_sec if max_sec is not None else cfg.OP_MAX_WAIT
    time.sleep(mn + random.random() * (mx - mn))


def human_click(page, selector: str, *, force: bool = False, delay: bool = True):
    """模拟人类点击：先移动鼠标到目标，再点击"""
    from playwright.sync_api import expect
    
    cfg = AntiDetectConfig
    
    # 找到元素
    el = page.locator(selector).first
    if not el:
        return False
    
    # 获取元素位置
    box = el.bounding_box()
    if not box:
        return False
    
    # 模拟鼠标移动到目标（带随机偏移）
    target_x = box["x"] + box["width"] * random.uniform(0.2, 0.8)
    target_y = box["y"] + box["height"] * random.uniform(0.2, 0.8)
    
    # 随机路径：先移动到附近，再精确到达
    mid_x = target_x + random.randint(-cfg.MOUSE_MAX_MOVE, cfg.MOUSE_MAX_MOVE)
    mid_y = target_y + random.randint(-cfg.MOUSE_MAX_MOVE, cfg.MOUSE_MAX_MOVE)
    
    try:
        page.mouse.move(mid_x, mid_y)
        time.sleep(random.uniform(0.05, 0.2))
        page.mouse.move(target_x, target_y)
        time.sleep(random.uniform(0.02, 0.08))
    except Exception:
        pass
    
    # 点击
    el.click(force=force, delay=random.randint(cfg.MOUSE_MIN_DELAY_MS, cfg.MOUSE_MAX_DELAY_MS))
    
    if delay:
        human_delay()
    
    return True


def human_type(page, selector: str, text: str, *, delay: bool = True):
    """模拟人类打字：逐个字符带随机间隔"""
    cfg = AntiDetectConfig
    
    el = page.locator(selector).first
    if not el:
        return False
    
    # 先点击输入框
    human_click(page, selector, delay=False)
    
    # 清空
    el.fill("")
    time.sleep(random.uniform(0.1, 0.3))
    
    # 逐字符输入（带随机延迟）
    for char in text:
        page.keyboard.insert_text(char)
        delay_ms = random.randint(cfg.TYPE_MIN_DELAY_MS, cfg.TYPE_MAX_DELAY_MS)
        time.sleep(delay_ms / 1000)
    
    if delay:
        human_delay()
    
    return True


def human_scroll(page, direction: str = "down", *, amount: Optional[int] = None):
    """模拟人类滚动页面"""
    cfg = AntiDetectConfig
    
    if amount is None:
        amount = random.randint(cfg.SCROLL_MIN_PX, cfg.SCROLL_MAX_PX)
    
    if direction == "down":
        page.evaluate(f"window.scrollBy(0, {amount})")
    else:
        page.evaluate(f"window.scrollBy(0, -{amount})")
    
    # 滚动后停顿（像人在阅读）
    time.sleep(random.uniform(0.5, 2.0))


def human_scroll_to_bottom(page, *, step_min: int = None, step_max: int = None):
    """模拟人类分步滚到底部，每步停顿"""
    cfg = AntiDetectConfig
    smin = step_min or cfg.SCROLL_MIN_PX
    smax = step_max or cfg.SCROLL_MAX_PX
    
    for _ in range(random.randint(3, 8)):
        step = random.randint(smin, smax)
        try:
            page.evaluate(f"window.scrollBy(0, {step})")
        except Exception:
            break
        time.sleep(random.uniform(0.3, 1.2))


def human_wait_page_ready(page, *, min_sec: float = 1.0, extra: float = None):
    """等待页面加载 + 额外随机时间（模拟阅读）"""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    
    extra = extra if extra is not None else random.uniform(0.5, 2.0)
    time.sleep(min_sec + extra)


# ══════════════════════════════════════════════════
# 行为记录 & 回放（让操作模式进一步随机化）
# ══════════════════════════════════════════════════

class BehaviorRecorder:
    """记录当前session的行为模式，避免每次行为完全一致"""
    
    def __init__(self):
        self._action_count = 0
        self._last_actions: list[str] = []
        self._speed_profile = random.uniform(0.7, 1.3)  # 速度偏移系数
        
    def record(self, action: str):
        self._action_count += 1
        self._last_actions.append(action)
        if len(self._last_actions) > 10:
            self._last_actions.pop(0)
    
    def should_delay_more(self) -> bool:
        """根据操作次数决定是否增加延迟（防止频繁操作）"""
        return self._action_count > 5 and random.random() < 0.3
    
    def get_speed(self) -> float:
        """获取当前速度系数"""
        if self._action_count > 20:
            return self._speed_profile * 0.8  # 长任务可略快
        return self._speed_profile


# ══════════════════════════════════════════════════
# 高级包装：全自动人类模拟页面
# ══════════════════════════════════════════════════

class HumanPage:
    """Page的包装类，所有操作默认启用人类行为模拟"""
    
    def __init__(self, page, recorder: Optional[BehaviorRecorder] = None):
        self._page = page
        self._recorder = recorder or BehaviorRecorder()
    
    @property
    def page(self):
        return self._page
    
    def goto(self, url: str, **kwargs):
        """带随机延迟的页面导航"""
        human_delay(1.0, 2.5)
        kwargs.setdefault("wait_until", "domcontentloaded")
        kwargs.setdefault("timeout", 30000)
        self._page.goto(url, **kwargs)
        self._recorder.record(f"goto:{url}")
        human_wait_page_ready(self._page)
    
    def click(self, selector: str, **kwargs):
        """模拟人类点击"""
        kwargs.setdefault("delay", True)
        ok = human_click(self._page, selector, **kwargs)
        if ok:
            self._recorder.record(f"click:{selector}")
        return ok
    
    def type(self, selector: str, text: str, **kwargs):
        """模拟人类打字"""
        ok = human_type(self._page, selector, text, **kwargs)
        if ok:
            self._recorder.record(f"type:{selector}")
        return ok
    
    def scroll(self, direction="down", **kwargs):
        """模拟人类滚动"""
        human_scroll(self._page, direction, **kwargs)
        self._recorder.record(f"scroll:{direction}")
    
    def scroll_to_bottom(self, **kwargs):
        """逐步滚动到底部"""
        human_scroll_to_bottom(self._page, **kwargs)
        self._recorder.record("scroll:bottom")
    
    def scroll_to_element(self, selector: str):
        """模拟人类滚动寻找元素（而不是直接 scroll_into_view_if_needed）"""
        try:
            el = self._page.locator(selector).first
            if el:
                box = el.bounding_box()
                if box:
                    # 分段滚动到元素附近
                    current_y = self._page.evaluate("window.scrollY")
                    target_y = box["y"] - random.randint(100, 300)
                    diff = target_y - current_y
                    if diff > 0:
                        steps = max(2, int(diff / 200))
                        step_size = diff / steps
                        for _ in range(steps):
                            self._page.evaluate(f"window.scrollBy(0, {step_size})")
                            time.sleep(random.uniform(0.2, 0.6))
                    self._recorder.record(f"scroll_to:{selector}")
            human_delay(0.5, 1.0)
        except Exception:
            pass
    
    def screenshot(self, path: str):
        """截图（带随机延迟，模拟看完再截）"""
        human_delay(0.5, 1.5)
        self._page.screenshot(path=path)
    
    def content(self) -> str:
        return self._page.content()
    
    def evaluate(self, js: str):
        return self._page.evaluate(js)
    
    def wait_for_timeout(self, ms: int):
        self._page.wait_for_timeout(ms)
    
    def url(self) -> str:
        return self._page.url
