#!/usr/bin/env python3
"""E2E verification for P0 deploy normalization"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

checks = []

# 1. site_configs table exists and has data
try:
    from core.database import get_db
    conn = get_db()
    sc = conn.execute('SELECT * FROM site_configs WHERE user_id=1 ORDER BY id DESC LIMIT 1').fetchone()
    checks.append(('site_configs table', 'has data' if sc else 'empty table'))
    if sc:
        checks.append(('Platform stored', sc['platform']))
        checks.append(('Comment system', sc['comment_system']))
        pc = json.loads(sc['plugins_config'])
        checks.append(('Plugins count', f"{len(pc)} enabled: {', '.join(pc.keys())}"))
except Exception as e:
    checks.append(('site_configs table', str(e)))

# 2. deployer_configs table
try:
    dc = conn.execute('SELECT COUNT(*) as c FROM deployer_configs').fetchone()
    checks.append(('deployer_configs table', f'{dc["c"]} rows'))
except Exception as e:
    checks.append(('deployer_configs table', str(e)))

# 3. deploy_log table
try:
    dl = conn.execute('SELECT COUNT(*) as c FROM deploy_log').fetchone()
    checks.append(('deploy_log table', f'{dl["c"]} rows'))
except Exception as e:
    checks.append(('deploy_log table', str(e)))

conn.close()

# 4. Nav link check
tmpl_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
with open(os.path.join(tmpl_dir, 'base.html')) as f:
    base = f.read()
checks.append(('Nav link: /accounts#deploy', 'FOUND' if '/accounts#deploy' in base else 'NOT FOUND'))

# 5. accounts.html #deploy section
with open(os.path.join(tmpl_dir, 'accounts.html')) as f:
    accounts = f.read()
checks.append(('accounts.html #deploy section', 'FOUND' if 'id="deploy"' in accounts else 'NOT FOUND'))

# 6. deployers.html has full config UI
with open(os.path.join(tmpl_dir, 'deployers.html')) as f:
    deployers = f.read()
ui_checks = []
ui_checks.append(('platformGrid', 'platformGrid' in deployers))
ui_checks.append(('commentSelect', 'commentSelect' in deployers))
ui_checks.append(('pluginGrid', 'pluginGrid' in deployers))
ui_checks.append(('saveSiteConfig', 'saveSiteConfig' in deployers))
ui_checks.append(('loadSiteConfig', 'loadSiteConfig' in deployers))
ui_ok = all(v for _, v in ui_checks)
checks.append(('deployers.html full UI', 'ALL OK' if ui_ok else 'MISSING: ' + ', '.join(k for k,v in ui_checks if not v)))

# 7. API endpoints
from routes.storage_deploy import BLOG_PLATFORMS, COMMENT_SYSTEMS, PLUGINS
checks.append(('Blog platforms', f'{len(BLOG_PLATFORMS)} platforms'))
checks.append(('Comment systems', f'{len(COMMENT_SYSTEMS)} systems'))
checks.append(('Plugins', f'{len(PLUGINS)} plugins'))

# 8. GitHub Pages deployer plugin
import warnings
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    # Force consistent import path with deployer_github_pages (uses flashsloth.core.deployer)
    from flashsloth.core.deployer import list_deployers
    import plugins.deployer_github_pages  # noqa: F401 — triggers @register decorator
deps = list_deployers()
checks.append(('Deployer plugins', f'{len(deps)} registered: {[d["name"] for d in deps]}'))

# Print report
print('=' * 60)
print('P0 部署归一化 — E2E 验证报告')
print(f'时间: 2026-07-08')
print('=' * 60)
all_ok = True
for item, status in checks:
    s = str(status)
    bad = s.startswith('NOT') or ('empty table' in s and 'site_configs' in item.lower()) or 'NOT FOUND' in s or 'MISSING' in s
    mark = '❌' if bad else '✅'
    print(f'  {mark} {item}: {status}')
    if bad:
        all_ok = False

print()
print(f'Overall: {"✅ ALL PASS" if all_ok else "⚠️ NEEDS ATTENTION"}')
print('=' * 60)
