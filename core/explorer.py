"""
FlashSloth Explorer — 可复用的平台探索器模块

用于 Playwright 自动探索论坛/平台的版块结构、发帖规则、上传限制等。
探索结果存入 forum_exploration 数据库表，同时缓存到 platform_reports/*.json。

设计目标：
1. 可被用户手动调用（通过 Web UI）
2. 可被 AI Agent 自主调用（通过 scheduler/cron）
3. 统一的探索结果格式，所有平台共用
4. 自动缓存，避免重复探索

使用方式：
    from core.explorer import explore_forum, explore_platform
    
    # 探索论坛版块
    result = explore_forum("amobbs.com", cookies, site_url="https://www.amobbs.com")
    
    # 探索平台分类/类型
    result = explore_platform("oshwhub.com", cookies, site_url="https://oshwhub.com")
"""

import json
import os
import re
import sqlite3
from typing import Optional


def get_db():
    """获取数据库连接（复用 core.database 的 DB_PATH）"""
    from flashsloth.core.database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def save_to_database(domain: str, platform_name: str, sections: dict, postable_fids: list):
    """将探索结果存入 forum_exploration 表"""
    conn = get_db()
    count = 0
    for fid, info in sections.items():
        can_post = fid in postable_fids
        if not can_post:
            continue
        name = info.get("name", f"fid={fid}")
        keywords = json.dumps([name], ensure_ascii=False)
        extra = json.dumps({
            "href": info.get("href", ""),
            "postable": True,
        }, ensure_ascii=False)
        
        try:
            conn.execute(
                """INSERT OR REPLACE INTO forum_exploration 
                   (platform, platform_domain, section_id, section_name, can_post, keywords, extra_info, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?, ?, datetime('now'))""",
                (platform_name, domain, fid, name, keywords, extra)
            )
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count


def save_to_json(domain: str, sections: dict, postable_fids: list):
    """将探索结果缓存到 JSON 文件"""
    out = {
        "site_url": f"https://{domain}",
        "total_forums": len(sections),
        "postable_forums": len(postable_fids),
        "forums": sections,
        "postable_fids": sorted(postable_fids, key=int) if postable_fids else [],
    }
    
    # 文件名用域名前缀
    prefix = domain.replace(".", "_")
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_reports")
    os.makedirs(reports_dir, exist_ok=True)
    out_path = os.path.join(reports_dir, f"{prefix}_forums.json")
    
    with open(out_path, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    
    return out_path


def explore_forum(domain: str, cookie_str: str, site_url: str = "") -> dict:
    """
    探索 Discuz 论坛版块结构
    
    Args:
        domain: 域名 (e.g. 'amobbs.com')
        cookie_str: Cookie 字符串
        site_url: 站点 URL (如不提供则自动拼接)
        
    Returns:
        {"success": bool, "forums": dict, "postable": list, "count": int}
    """
    from playwright.sync_api import sync_playwright
    
    if not site_url:
        site_url = f"https://{domain}"
    
    result = {"success": False, "forums": {}, "postable": [], "count": 0, "error": ""}
    
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            ctx = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            
            # 注入 cookie
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    n, v = pair.split("=", 1)
                    ctx.add_cookies([{"name": n, "value": v, "domain": f".{domain}", "path": "/"}])
            
            page = ctx.new_page()
            
            # Step 1: 爬取版块列表
            page.goto(f"{site_url}/forum.php", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            
            all_links = page.query_selector_all("a")
            seen = {}
            
            for a in all_links:
                href = a.get_attribute("href") or ""
                text = a.inner_text().strip()
                fid = None
                for m in [re.search(r'fid=(\d+)', href), re.search(r'forum-(\d+)', href)]:
                    if m:
                        fid = m.group(1)
                        break
                if fid and text and len(text) < 60:
                    if fid not in seen:
                        seen[fid] = {"name": text, "href": href}
            
            # Step 2: 测试发帖权限（抽样，最多测试50个）
            postable = []
            test_list = list(seen.keys())[:50]
            for fid in test_list:
                try:
                    page.goto(
                        f"{site_url}/forum.php?mod=post&action=newthread&fid={fid}",
                        wait_until="domcontentloaded", timeout=10000
                    )
                    page.wait_for_timeout(800)
                    has_form = page.query_selector("input[name='subject']") is not None
                    body_text = page.inner_text("body")[:200]
                    can_post = has_form and "抱歉" not in body_text and "没有权限" not in body_text
                    seen[fid]["can_post"] = can_post
                    if can_post:
                        postable.append(fid)
                except Exception:
                    seen[fid]["can_post"] = False
            
            browser.close()
            
            result["success"] = True
            result["forums"] = seen
            result["postable"] = postable
            result["count"] = len(seen)
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


def explore_csdn(cookie_str: str) -> dict:
    """
    探索 CSDN 编辑器分类
    
    注意: CSDN 不是论坛，没有 FID。只返回可用分类和设置。
    """
    return {
        "success": True,
        "type": "blog",
        "categories": ["原创", "转载", "翻译"],
        "has_categories": True,
        "has_tags": True,
    }


def explore_oshwhub(cookie_str: str) -> dict:
    """
    探索 OSHWHub 项目类型
    """
    return {
        "success": True,
        "type": "project_platform",
        "project_types": [
            {"id": "project", "name": "工程", "endpoint": "/project/create"},
            {"id": "article", "name": "文章", "endpoint": "/article/create"},
        ],
        "tags": [
            "5G/5G技术", "智能硬件", "课设/毕设", "DIY设计", "汽车电子",
            "消费电子", "工业电子", "家用电子", "医疗电子", "开源复刻",
            "电力电子", "电路仿真", "测量仪表", "电工电子", "电路模块",
            "3D打印", "CNC加工", "FPC软板", "方案验证板", "功能模块", "成品/套件",
        ],
    }
