"""
Consolidate forum exploration data.
- Remove www-prefixed duplicates
- Keep the better (newer) data under the non-www domain
- Update JSON filenames to match
"""
import sqlite3, os, json, shutil

db_path = os.path.expanduser('~/.hermes/flashsloth/flashsloth.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

reports_dir = os.path.expanduser('~/.hermes/flashsloth/platform_reports')

# 1. Migrate www data to non-www domain
for www_domain, clean_domain in [('www.amobbs.com', 'amobbs.com'), ('www.mydigit.cn', 'mydigit.cn')]:
    # Get new data
    new_rows = conn.execute(
        "SELECT * FROM forum_exploration WHERE platform_domain=?", (www_domain,)
    ).fetchall()
    # Get old data
    old_ids = set(
        r['section_id'] for r in conn.execute(
            "SELECT section_id FROM forum_exploration WHERE platform_domain=?", (clean_domain,)
        ).fetchall()
    )
    
    # For each new record, upsert into clean domain
    updated = 0
    inserted = 0
    now = __import__('time').strftime('%Y-%m-%d %H:%M:%S')
    
    for r in new_rows:
        if r['section_id'] in old_ids and clean_domain == r['platform_domain']:
            # Already exists under clean domain
            continue
        
        existing = conn.execute(
            "SELECT id FROM forum_exploration WHERE platform_domain=? AND section_id=?",
            (clean_domain, r['section_id'])
        ).fetchone()
        
        if existing:
            conn.execute("""
                UPDATE forum_exploration SET section_name=?, can_post=?, keywords=?, extra_info=?, updated_at=?
                WHERE id=?
            """, (r['section_name'], r['can_post'], r['keywords'], r['extra_info'], now, existing['id']))
            updated += 1
        else:
            conn.execute("""
                INSERT INTO forum_exploration (platform, platform_domain, section_id, section_name, can_post, keywords, extra_info, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (r['platform'], clean_domain, r['section_id'], r['section_name'], 
                  r['can_post'], r['keywords'], r['extra_info'], now, now))
            inserted += 1
    
    print(f"{www_domain} -> {clean_domain}: updated={updated}, inserted={inserted}")
    
    # Delete www-prefixed records
    conn.execute("DELETE FROM forum_exploration WHERE platform_domain=?", (www_domain,))
    print(f"  Deleted {www_domain} records")

conn.commit()

# 2. Update JSON files - merge www files into clean domain files
for www_prefix, clean_key in [('www_amobbs_com', 'amobbs'), ('www_mydigit_cn', 'mydigit')]:
    www_json = os.path.join(reports_dir, f'{www_prefix}_forums.json')
    clean_json = os.path.join(reports_dir, f'{clean_key}_forums.json')
    
    if os.path.exists(www_json):
        with open(www_json) as f:
            new_data = json.load(f)
        
        # Fix site_url and save to clean filename
        new_data['site_url'] = new_data['site_url'].replace('https://www.', 'https://')
        clean_path = os.path.join(reports_dir, f'{clean_key}_forums.json')
        with open(clean_path, 'w') as f:
            json.dump(new_data, f, ensure_ascii=False, indent=2)
        
        # Remove www file
        os.remove(www_json)
        print(f"  JSON: {www_json} -> merged into {clean_key}_forums.json")

# 3. Verify final counts
for domain in ['amobbs.com', 'mydigit.cn', 'oshwhub.com']:
    cnt = conn.execute(
        "SELECT COUNT(*) as c FROM forum_exploration WHERE platform_domain=?", (domain,)
    ).fetchone()['c']
    print(f"  {domain}: {cnt} records")

conn.close()
print("\nConsolidation complete!")
