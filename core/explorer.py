"""FlashSloth — Playwright 论坛探索引擎
可复用：检测论坛类型 → 爬取版块列表 → 保存到 forum_exploration 表
防风特性：继承 core/anti_detect 模块的所有人类行为模拟
资源节约：每域名每小时最多探索一次，全局限流
"""
import json, time, os, sys, re, random, threading, sqlite3
from pathlib import Path
from typing import Optional
from flashsloth.core.anti_detect import (
    create_human_context, HumanPage, BehaviorRecorder,
    human_delay, human_wait_page_ready, human_scroll,
)

MAX_OPS = 8

# ─── 全局限流器 ───────────────────────
_EXPLORE_LOCK = threading.Lock()
_EXPLORE_HISTORY: dict[str, float] = {}  # domain → last_explore_timestamp (内存缓存)
_MIN_INTERVAL_SECONDS = 3600  # 每个域名最少间隔1小时
_DB_PATH_CACHE = None  # 数据库路径缓存


def _get_db_path() -> str:
    """获取数据库路径"""
    global _DB_PATH_CACHE
    if _DB_PATH_CACHE is None:
        _DB_PATH_CACHE = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "flashsloth.db"
        )
    return _DB_PATH_CACHE


def _init_cooldown_table():
    """确保 explore_cooldown 表存在（原子创建，幂等）"""
    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute("""CREATE TABLE IF NOT EXISTS explore_cooldown (
            domain TEXT PRIMARY KEY,
            last_explore_at REAL NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠️ 初始化限流表失败: {e}")


def _get_db_last_explore(domain: str) -> float:
    """从数据库查询域名的最后探索时间"""
    try:
        conn = sqlite3.connect(_get_db_path())
        row = conn.execute(
            "SELECT last_explore_at FROM explore_cooldown WHERE domain=?",
            (domain,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0.0
    except Exception:
        return 0.0


def _set_db_last_explore(domain: str, timestamp: float):
    """在数据库中记录域名的探索时间（跨进程持久化）"""
    try:
        conn = sqlite3.connect(_get_db_path())
        conn.execute(
            "INSERT OR REPLACE INTO explore_cooldown (domain, last_explore_at, updated_at) "
            "VALUES (?, ?, datetime('now'))",
            (domain, timestamp)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  ⚠️ 写入限流记录失败: {e}")


def can_explore(domain: str) -> bool:
    """检查域名是否可探索（频率限制）- 只检查不记录

    双缓存策略：
    1. 内存检查（同进程内防重复）
    2. DB检查（跨进程持久化，cron 等独立进程共享）
    """
    global _EXPLORE_HISTORY
    now = time.time()

    # ── 1. 内存检查（同进程内防重复） ──
    with _EXPLORE_LOCK:
        last_in_mem = _EXPLORE_HISTORY.get(domain, 0)
        if now - last_in_mem < _MIN_INTERVAL_SECONDS:
            remaining = int(_MIN_INTERVAL_SECONDS - (now - last_in_mem))
            print(f"  ⏳ 探索限流(内存): {domain} 还需等待 {remaining}s")
            return False

    # ── 2. DB检查（跨进程持久化） ──
    _init_cooldown_table()
    last_in_db = _get_db_last_explore(domain)
    if last_in_db > 0 and now - last_in_db < _MIN_INTERVAL_SECONDS:
        remaining = int(_MIN_INTERVAL_SECONDS - (now - last_in_db))
        print(f"  ⏳ 探索限流(DB): {domain} 还需等待 {remaining}s")
        # 同步到内存缓存
        with _EXPLORE_LOCK:
            _EXPLORE_HISTORY[domain] = last_in_db
        return False

    return True


def mark_explored(domain: str):
    """探索成功后调用——在内存 + DB 中同时记录探索时间

    与 can_explore() 分离为两步，避免探索失败时浪费限流槽位。
    """
    global _EXPLORE_HISTORY
    now = time.time()
    with _EXPLORE_LOCK:
        _EXPLORE_HISTORY[domain] = now
    _init_cooldown_table()
    _set_db_last_explore(domain, now)
    print(f"  ✅ 已记录 {domain} 的探索时间 ({time.strftime('%H:%M:%S')})")


def get_explore_cooldown(domain: str) -> int:
    """获取域名冷却剩余秒数（合并内存+DB）"""
    global _EXPLORE_HISTORY
    now = time.time()

    # 先查内存（更快）
    with _EXPLORE_LOCK:
        last = _EXPLORE_HISTORY.get(domain, 0)

    # 内存没有则查DB
    if last == 0:
        last = _get_db_last_explore(domain)

    remaining = int(_MIN_INTERVAL_SECONDS - (now - last))
    return max(0, remaining)


def _get_human_context(browser):
    """创建带防风特性的浏览器上下文（供所有平台使用）"""
    return create_human_context(browser)


def _get_human_page(page) -> HumanPage:
    """包装为 HumanPage（所有操作自动模拟人类）"""
    return HumanPage(page)


def _check_banned(page) -> bool:
    """检查是否被反爬"""
    url = page.url.lower()
    body = page.content()[:800].lower()
    signals = ["418", "429", "403", "too many requests", "rate limit",
               "blocked", "captcha", "验证码", "拒绝访问", "频繁", "安全验证"]
    for s in signals:
        if s in body or s in url:
            return True
    return False


def _detect_platform_type(page) -> str:
    """检测网站平台类型"""
    html = page.content().lower()
    if "discuz" in html or "forum.php" in page.url.lower() or "comiis" in html:
        return "discuz"
    if "wp-content" in html or "wordpress" in html:
        return "wordpress"
    if "zhihu" in page.url.lower():
        return "zhihu"
    if "juejin" in page.url.lower():
        return "juejin"
    if "csdn" in page.url.lower():
        return "csdn"
    if "bilibili" in page.url.lower():
        return "bilibili"
    if "oshwhub" in page.url.lower() or "jlc" in page.url.lower():
        return "oshwhub"
    return "unknown"


def explore_discuz_forums(page, site_url: str, domain: str) -> list:
    """探索 Discuz 论坛版块列表"""
    sections = []

    # OP1: 访问 forum.php
    page.goto(f"{site_url}/forum.php", wait_until="domcontentloaded", timeout=30000)
    human_delay()
    if _check_banned(page):
        return sections

    # 提取版块信息 — Discuz 版块链接格式: forum.php?mod=forumdisplay&fid=N
    links = page.eval_on_selector_all(
        "a[href*='forum.php?mod=forumdisplay']",
        "els => els.map(el => ({href: el.href, text: el.innerText.trim()}))"
    )
    seen_fids = set()
    for l in links:
        m = re.search(r'fid=(\d+)', l["href"])
        if m:
            fid = m.group(1)
            name = l["text"] or f"fid={fid}"
            if fid not in seen_fids and name:
                seen_fids.add(fid)
                sections.append({
                    "section_id": fid,
                    "section_name": name,
                    "can_post": True,
                    "keywords": json.dumps([name], ensure_ascii=False),
                    "extra_info": json.dumps({
                        "href": f"/forum.php?mod=forumdisplay&fid={fid}",
                        "postable": True,
                    }, ensure_ascii=False),
                })

    # 也试试另一种 selector（某些Discuz版块是 js 加载的）
    if len(sections) < 3:
        all_links = page.eval_on_selector_all(
            "a[href*='forum-'], a[href*='fid=']",
            "els => els.map(el => ({href: el.href, text: el.innerText.trim()}))"
        )
        for l in all_links:
            m = re.search(r'fid=(\d+)', l["href"])
            if not m:
                m = re.search(r'forum-(\d+)', l["href"])
            if m:
                fid = m.group(1)
                name = l["text"] or f"fid={fid}"
                if fid not in seen_fids and name:
                    seen_fids.add(fid)
                    sections.append({
                        "section_id": fid,
                        "section_name": name,
                        "can_post": True,
                        "keywords": json.dumps([name], ensure_ascii=False),
                        "extra_info": json.dumps({
                            "href": l["href"],
                            "postable": True,
                        }, ensure_ascii=False),
                    })

    return sections


def save_exploration_results(conn, platform: str, domain: str, sections: list, capabilities: Optional[dict] = None):
    """保存探索结果到 forum_exploration + platform_config"""
    for s in sections:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO forum_exploration 
                   (platform, platform_domain, section_id, section_name, can_post, keywords, extra_info)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (platform, domain, s["section_id"], s["section_name"],
                 1 if s.get("can_post") else 0,
                 s.get("keywords", "[]"),
                 s.get("extra_info", "{}"))
            )
        except Exception as e:
            print(f"  插入失败 {domain}/{s['section_id']}: {e}")
    conn.commit()

    if capabilities:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO platform_config (platform, platform_domain, config_json) VALUES (?, ?, ?)",
                (platform, domain, json.dumps(capabilities, ensure_ascii=False))
            )
            conn.commit()
        except Exception as e:
            print(f"  保存能力配置失败: {e}")

    # 探索成功，记录限流时间（DB持久化，跨进程共享）
    try:
        mark_explored(domain)
    except Exception as e:
        print(f"  记录探索时间失败: {e}")

    print(f"  探索完成: {len(sections)} 个版块已保存")
