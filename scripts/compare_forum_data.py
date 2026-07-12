import sqlite3, os, json

db_path = os.path.expanduser('~/.hermes/flashsloth/flashsloth.db')
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Compare old vs new amobbs data
new = conn.execute("SELECT section_id, section_name FROM forum_exploration WHERE platform_domain='www.amobbs.com' ORDER BY section_id").fetchall()
old = conn.execute("SELECT section_id, section_name FROM forum_exploration WHERE platform_domain='amobbs.com' ORDER BY section_id").fetchall()

print(f"amobbs 旧数据: {len(old)} 条")
print(f"amobbs 新数据(含www): {len(new)} 条")

old_ids = set(r['section_id'] for r in old)
new_ids = set(r['section_id'] for r in new)
only_old = old_ids - new_ids
only_new = new_ids - old_ids

if only_old:
    print(f"\n旧数据独有 ({len(only_old)}):")
    for sid in sorted(only_old):
        name = [r['section_name'] for r in old if r['section_id'] == sid][0]
        print(f"  {sid}: {name}")

if only_new:
    print(f"\n新数据独有 ({len(only_new)}):")
    for sid in sorted(only_new):
        name = [r['section_name'] for r in new if r['section_id'] == sid][0]
        print(f"  {sid}: {name}")

# Compare mydigit
new_m = conn.execute("SELECT section_id, section_name FROM forum_exploration WHERE platform_domain='www.mydigit.cn' ORDER BY section_id").fetchall()
old_m = conn.execute("SELECT section_id, section_name FROM forum_exploration WHERE platform_domain='mydigit.cn' ORDER BY section_id").fetchall()

print(f"\n\nmydigit 旧数据: {len(old_m)} 条")
print(f"mydigit 新数据(含www): {len(new_m)} 条")

old_m_ids = set(r['section_id'] for r in old_m)
new_m_ids = set(r['section_id'] for r in new_m)
only_old_m = old_m_ids - new_m_ids
only_new_m = new_m_ids - old_m_ids

if only_old_m:
    print(f"\n旧数据独有 ({len(only_old_m)}):")
    for sid in sorted(only_old_m):
        name = [r['section_name'] for r in old_m if r['section_id'] == sid][0]
        print(f"  {sid}: {name}")

if only_new_m:
    print(f"\n新数据独有 ({len(only_new_m)}):")
    for sid in sorted(only_new_m):
        name = [r['section_name'] for r in new_m if r['section_id'] == sid][0]
        print(f"  {sid}: {name}")

print("\n\n结论:")
print(f"  amobbs: 旧{len(old)}条 vs 新{len(new)}条 -> {'相同' if old_ids == new_ids else '有差异'}")
print(f"  mydigit: 旧{len(old_m)}条 vs 新{len(new_m)}条 -> {'相同' if old_m_ids == new_m_ids else '有差异'}")

conn.close()
