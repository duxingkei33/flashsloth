"""FlashSloth — Playwright 论坛探索引擎
可复用：检测论坛类型 → 爬取版块列表 → 保存到 forum_exploration 表
防风特性：继承 core/anti_detect 模块的所有人类行为模拟
"""
import json, time, os, sys, re, random
from typing import Optional
from flashsloth.core.anti_detect import (
    create_human_context, HumanPage, BehaviorRecorder,
    human_delay, human_wait_page_ready, human_scroll,
)

MAX_OPS = 8


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

    print(f"  探索完成: {len(sections)} 个版块已保存")
