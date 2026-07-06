"""Sync forum_registry keywords to forum_exploration DB."""
import sys, json, os, importlib

sys.path.insert(0, os.path.expanduser('~/.hermes/flashsloth'))
import core.forum_registry
importlib.reload(core.forum_registry)
from core.forum_registry import FORUM_DATA

import sqlite3
db_path = os.path.expanduser('~/.hermes/flashsloth/flashsloth.db')
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

updated = 0
for domain, forums in FORUM_DATA.items():
    for fid, info in forums.items():
        keywords = info.get('keywords', [info['name'].lower()])
        db.execute(
            "UPDATE forum_exploration SET keywords=? WHERE platform_domain=? AND section_id=?",
            (json.dumps(keywords, ensure_ascii=False), domain, fid)
        )
        updated += 1

db.commit()

rows = db.execute("SELECT platform_domain, COUNT(*) as cnt FROM forum_exploration GROUP BY platform_domain").fetchall()
print("Updated forum_exploration:")
for r in rows:
    print(f"  {r['platform_domain']}: {r['cnt']} records")
print(f"Total records updated: {updated}")
db.close()
