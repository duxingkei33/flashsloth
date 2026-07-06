"""
Hourly incremental forum exploration script.
Visits Discuz forum homepages, checks if section list changed,
updates forum_exploration DB if needed.

Usage: PYTHONPATH=~/.hermes python3 scripts/hourly_forum_check.py
"""

import sys
import os
import json
import time
import hashlib
import re
import random

# Ensure project root is in path
sys.path.insert(0, os.path.expanduser('~/.hermes'))

# Use FS venv python, not system python
VENV_PYTHON = os.path.expanduser('~/.hermes/flashsloth/venv/bin/python3')

def get_db():
    """Get sqlite3 connection."""
    import sqlite3
    db_path = os.path.expanduser('~/.hermes/flashsloth/flashsloth.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_accounts(platform_type=None):
    """Get active platform accounts from DB."""
    conn = get_db()
    accounts = []
    rows = conn.execute('''
        SELECT id, platform, account_name, config_json
        FROM platform_accounts
        WHERE is_active=1 OR is_active IS NULL
        ORDER BY platform, id
    ''').fetchall()
    
    for r in rows:
        cfg = json.loads(r['config_json']) if isinstance(r['config_json'], str) else {}
        site_url = cfg.get('site_url', '')
        cookie = cfg.get('cookie', '')
        username = cfg.get('username', '')
        
        # Determine if Discuz
        platform = r['platform']
        is_discuz = platform == 'discuz'
        
        if platform_type and platform != platform_type:
            continue
            
        accounts.append({
            'db_id': r['id'],
            'platform': platform,
            'is_discuz': is_discuz,
            'account_name': r['account_name'],
            'site_url': site_url,
            'cookie': cookie,
            'username': username,
        })
    
    conn.close()
    return accounts

def get_existing_forum_data(platform_domain):
    """Get current forum_exploration data for this domain."""
    conn = get_db()
    rows = conn.execute('''
        SELECT section_id, section_name, can_post, keywords, extra_info
        FROM forum_exploration
        WHERE platform_domain=?
        ORDER BY section_id
    ''', (platform_domain,)).fetchall()
    
    forums = {}
    for r in rows:
        forums[r['section_id']] = {
            'name': r['section_name'],
            'can_post': bool(r['can_post']),
            'keywords': r['keywords'],
            'extra_info': r['extra_info'],
        }
    
    conn.close()
    return forums

def check_ban(page):
    """Check if page shows ban/captcha signals."""
    try:
        content = page.content()[:1000].lower()
        url = page.url.lower()
    except:
        return False
    
    signals = [
        "418", "429", "403", "too many requests", "rate limit",
        "blocked", "captcha", "验证码", "拒绝访问", "频繁",
        "安全验证", "access denied", "human verification",
        "cf-browser-verify", "challenge-platform",
    ]
    for s in signals:
        if s in content[:500] or s in url:
            return True
    return False

def load_json_forums(domain):
    """Load forum data from platform_reports JSON file."""
    domain_key = domain.replace('.', '_')
    json_path = os.path.expanduser(f'~/.hermes/flashsloth/platform_reports/{domain_key}_forums.json')
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)
    return None

def save_json_forums(domain, data):
    """Save forum data to JSON file."""
    os.makedirs(os.path.expanduser('~/.hermes/flashsloth/platform_reports'), exist_ok=True)
    domain_key = domain.replace('.', '_')
    json_path = os.path.expanduser(f'~/.hermes/flashsloth/platform_reports/{domain_key}_forums.json')
    with open(json_path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✅ JSON saved to {json_path}")

def update_exploration_db(platform, domain, forums_dict):
    """Update forum_exploration table with new data."""
    conn = get_db()
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    
    updated = 0
    inserted = 0
    
    for fid, info in forums_dict.items():
        existing = conn.execute(
            'SELECT id FROM forum_exploration WHERE platform_domain=? AND section_id=?',
            (domain, str(fid))
        ).fetchone()
        
        extra_info = json.dumps(info.get('extra_info', {}), ensure_ascii=False)
        keywords_json = json.dumps(info.get('keywords', []), ensure_ascii=False)
        
        if existing:
            # Update
            conn.execute('''
                UPDATE forum_exploration 
                SET section_name=?, can_post=?, keywords=?, extra_info=?, updated_at=?
                WHERE id=?
            ''', (info['name'], 1 if info['can_post'] else 0, 
                  keywords_json, extra_info, now, existing['id']))
            updated += 1
        else:
            # Insert
            conn.execute('''
                INSERT INTO forum_exploration 
                (platform, platform_domain, section_id, section_name, can_post, keywords, extra_info, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (platform, domain, str(fid), info['name'],
                  1 if info['can_post'] else 0,
                  keywords_json, extra_info, now, now))
            inserted += 1
    
    conn.commit()
    conn.close()
    return updated, inserted

def explore_discuz(account):
    """
    Use Playwright to visit a Discuz forum homepage.
    Extracts section list and compares with existing data.
    Returns dict with results.
    """
    from playwright.sync_api import sync_playwright
    
    site_url = account['site_url'].rstrip('/')
    cookie_str = account['cookie']
    domain = site_url.replace('https://', '').replace('http://', '').split('/')[0]
    # Strip www. for consistent domain naming
    if domain.startswith('www.'):
        domain = domain[4:]
    
    print(f"\n  🔍 探索 {domain} ({account['account_name']})")
    print(f"  URL: {site_url}")
    
    result = {
        'domain': domain,
        'account': account['account_name'],
        'sections_found': 0,
        'can_post_count': 0,
        'changed': False,
        'banned': False,
        'error': None,
        'forums': {},
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            
            ctx = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            )
            
            # Inject anti-detection
            ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh']});
            """)
            
            # Set cookies - strip www. from cookie domain too
            cookie_domain = domain
            if cookie_domain.startswith('www.'):
                cookie_domain = cookie_domain[4:]
            if cookie_str:
                for part in cookie_str.split(';'):
                    part = part.strip()
                    if '=' in part:
                        name, value = part.split('=', 1)
                        ctx.add_cookies([{
                            'name': name.strip(),
                            'value': value.strip(),
                            'domain': domain,
                            'path': '/',
                        }])
            
            page = ctx.new_page()
            page.set_default_timeout(30000)
            
            # Visit forum homepage
            time.sleep(random.uniform(1, 2))
            print(f"  📄 访问论坛首页...")
            try:
                page.goto(f"{site_url}/forum.php", wait_until='domcontentloaded', timeout=30000)
            except Exception as e:
                print(f"  ⚠️  goto timeout, trying simpler load: {e}")
                try:
                    page.goto(f"{site_url}/forum.php", wait_until='commit', timeout=15000)
                except Exception as e2:
                    result['error'] = f"Page load failed: {e2}"
                    browser.close()
                    return result
            
            time.sleep(random.uniform(2, 3))
            
            # Check for ban
            if check_ban(page):
                print(f"  🚫 被封杀/验证码!")
                result['banned'] = True
                browser.close()
                return result
            
            # Extract section list from forum.php
            # Discuz forum.php has a list of forums with links like forum-{fid}-1.html
            sections = {}
            
            # Method 1: Find all forum links matching forum-N-1.html or forumdisplay.php?fid=N
            forum_links = page.query_selector_all("a[href*='forum-'], a[href*='forumdisplay.php'], a[href*='forum.php?gid=']")
            
            for link in forum_links:
                try:
                    href = link.get_attribute('href') or ''
                    text = link.inner_text().strip()
                    
                    if not text or len(text) < 1:
                        continue
                    
                    # Extract FID from href - various Discuz patterns
                    fid = None
                    m = re.search(r'forum[=\-/](\d+)', href)
                    if m:
                        fid = m.group(1)
                    m = re.search(r'forumdisplay\.php\?fid=(\d+)', href)
                    if m:
                        fid = m.group(1)
                    m = re.search(r'forum\.php\?gid=(\d+)', href)
                    if m:
                        fid = f"g{m.group(1)}"  # Category, not a postable forum
                    
                    if fid and text:
                        full_href = href if href.startswith('http') else f"{site_url}/{href.lstrip('/')}"
                        sections[fid] = {
                            'name': text,
                            'href': full_href,
                            'can_post': True,  # Will validate later
                            'can_post_verified': False,
                        }
                except:
                    continue
            
            print(f"  📊 找到 {len(sections)} 个版块链接")
            
            # Method 2: Also try to get sections from forum list tables
            # Discuz usually has a specific structure for forum list
            # Look for <th> or <dt> elements with forum names
            th_elements = page.query_selector_all("th a[href*='forum-'], dt a[href*='forum-'], h2 a[href*='forum-']")
            for el in th_elements:
                try:
                    href = el.get_attribute('href') or ''
                    text = el.inner_text().strip()
                    m = re.search(r'forum[=\-/](\d+)', href)
                    if m and text:
                        fid = m.group(1)
                        if fid not in sections:
                            full_href = href if href.startswith('http') else f"{site_url}/{href.lstrip('/')}"
                            sections[fid] = {
                                'name': text,
                                'href': full_href,
                                'can_post': True,
                                'can_post_verified': False,
                            }
                except:
                    continue
            
            print(f"  📊 总共找到 {len(sections)} 个版块 (含类别)")
            
            # Categorize: Discuz forum groups (categories) vs postable sections
            postable = {}
            categories = {}
            for fid, info in sections.items():
                if fid.startswith('g'):
                    categories[fid] = info
                else:
                    postable[fid] = info
            
            result['sections_found'] = len(postable)
            result['forums'] = postable
            result['categories'] = categories
            
            browser.close()
            
    except Exception as e:
        result['error'] = str(e)
        print(f"  ❌ Error: {e}")
    
    return result

def main():
    """Main exploration routine."""
    print("=" * 60)
    print("  FlashSloth 平台探索 — 增量检测 (每小时)")
    print("=" * 60)
    print()
    
    # Get Discuz accounts
    accounts = get_accounts()
    discuz_accounts = [a for a in accounts if a['is_discuz']]
    
    print(f"Discuz 平台账号: {len(discuz_accounts)} 个")
    for a in discuz_accounts:
        print(f"  - {a['account_name']} ({a['site_url']}) [cookie: {'✅' if a['cookie'] else '❌'}]")
    
    if not discuz_accounts:
        print("没有 Discuz 账号，跳过探索。")
        return "[SILENT]"
    
    changes_detected = False
    results = []
    
    for idx, account in enumerate(discuz_accounts):
        if idx > 0:
            print(f"\n⏳ 等待30秒避免资源竞争...")
            time.sleep(30)
        
        domain = account['site_url'].replace('https://', '').replace('http://', '').split('/')[0]
        # Strip www. for consistent domain naming (DB stores bare domain)
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Load existing data
        existing = get_existing_forum_data(domain)
        json_data = load_json_forums(domain)
        
        print(f"\n现有数据: {len(existing)} 个版块在 DB, ", end='')
        if json_data:
            print(f"{json_data.get('total_forums', '?')} 个在 JSON")
        else:
            print("无 JSON 数据")
        
        # Do Playwright exploration
        result = explore_discuz(account)
        results.append(result)
        
        if result['error']:
            print(f"  ❌ 探索失败: {result['error']}")
            continue
        
        if result['banned']:
            print(f"  🚫 平台被封杀，跳过")
            continue
        
        # Compare with existing data
        new_forums = result['forums']
        existing_count = len(existing)
        new_count = len(new_forums)
        
        print(f"\n  📊 对比: DB有 {existing_count} 个版块, 实际找到 {new_count} 个")
        
        platform_changed = False
        
        if new_count == 0:
            print(f"  ⚠️ 未找到任何版块，可能解析失败，跳过更新")
            continue
        
        if existing_count != new_count:
            print(f"  🔄 版块数量变化! {existing_count} → {new_count}")
            platform_changed = True
        else:
            # Check if names changed by computing hash
            old_hash = hashlib.md5(
                json.dumps({fid: info['name'] for fid, info in existing.items()}, sort_keys=True).encode()
            ).hexdigest()
            new_hash = hashlib.md5(
                json.dumps({fid: info['name'] for fid, info in new_forums.items()}, sort_keys=True).encode()
            ).hexdigest()
            
            if old_hash != new_hash:
                print(f"  🔄 版块名称有变化!")
                platform_changed = True
            else:
                print(f"  ✅ 无变化 (hash 匹配)")
        
        if platform_changed:
            changes_detected = True
            print(f"  💾 准备更新数据...")
            
            # Update JSON
            platform_type = 'discuz'
            json_out = {
                'site_url': f'https://{domain}',
                'total_forums': new_count,
                'postable_forums': sum(1 for f in new_forums.values() if f['can_post']),
                'forums': {fid: {
                    'name': info['name'],
                    'href': info['href'],
                    'can_post': info['can_post'],
                } for fid, info in new_forums.items()},
                'last_explored': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            save_json_forums(domain, json_out)
            
            # Update DB
            updated, inserted = update_exploration_db(platform_type, domain, new_forums)
            print(f"  💾 DB: 更新 {updated} 条, 新增 {inserted} 条")
            
            # Clean up orphan sections (in DB but not found by Playwright)
            new_fids = set(new_forums.keys())
            existing_fids = set(existing.keys())
            orphans = existing_fids - new_fids
            if orphans:
                conn = get_db()
                deleted = conn.execute(
                    "DELETE FROM forum_exploration WHERE platform_domain=? AND section_id IN ({})".format(
                        ','.join(['?'] * len(orphans))),
                    [domain] + list(orphans)
                ).rowcount
                conn.commit()
                conn.close()
                print(f"  🧹 清理 {deleted} 个失效版块 (已从DB移除)")
        else:
            print(f"  ⏭️ 无变化，跳过数据库更新")
    
    print("\n" + "=" * 60)
    print(f"  探索完成！")
    
    if changes_detected:
        print(f"  ⚠️ 检测到变化，数据已更新")
    else:
        print(f"  ✅ 所有平台无变化")
    print("=" * 60)
    
    # Print summary
    print("\n📋 汇总:")
    for r in results:
        domain = r['domain']
        sections = r.get('sections_found', 0)
        banned = r.get('banned', False)
        error = r.get('error')
        status = "✅" if not banned and not error else ("🚫 被封" if banned else "❌ 错误")
        detail = f"{sections} 版块"
        if error:
            detail = error
        print(f"  {status} {domain}: {detail}")
    
    if not changes_detected:
        return "[SILENT]"
    
    return f"changes_detected: {len(discuz_accounts)} platforms checked"

if __name__ == '__main__':
    result = main()
    if result == "[SILENT]":
        print("[SILENT]")
    else:
        print(f"\nResult: {result}")
