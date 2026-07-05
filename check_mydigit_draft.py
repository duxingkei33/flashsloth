"""
检查数码之家 (mydigit.cn) 发帖页是否有存草稿功能
"""
import json, time, sys, os, re, sqlite3

SITE = "https://www.mydigit.cn"
db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "flashsloth.db"))
cur = db.cursor()
cur.execute("SELECT config_json FROM platform_accounts WHERE id=4")
cfg = json.loads(cur.fetchone()[0])
db.close()
COOKIE = cfg.get("cookie", "")

FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(user_agent="Mozilla/5.0", viewport={"width": 1920, "height": 1080})
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    for c in COOKIE.split("; "):
        if "=" in c:
            k, v = c.split("=", 1)
            ctx.add_cookies([{"name": k.strip(), "value": v.strip(), "domain": ".mydigit.cn", "path": "/"}])

    page = ctx.new_page()
    page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid=40", wait_until="networkidle", timeout=60000)
    time.sleep(2)

    print(f"页面标题: {page.title()}")
    
    # 找所有按钮
    buttons = page.query_selector_all("button, input[type='submit']")
    print(f"\n按钮列表:")
    for btn in buttons:
        text = (btn.inner_text() or btn.get_attribute("value") or "").strip()
        name = btn.get_attribute("name") or ""
        id_ = btn.get_attribute("id") or ""
        if text or name:
            print(f"  name={name} id={id_} text={text[:30]}")
    
    # 找所有隐藏字段
    hidden_inputs = page.query_selector_all("input[type='hidden']")
    print(f"\n隐藏字段:")
    for inp in hidden_inputs:
        name = inp.get_attribute("name") or ""
        val = inp.get_attribute("value") or ""
        if name:
            print(f"  {name} = {val[:30]}")
    
    # 搜索页面源码中是否有"保存草稿"或"draft"
    html = page.content()
    if "保存草稿" in html or "draft" in html.lower() or "save" in html.lower():
        print(f"\n✅ 发现草稿相关关键词")
        # 提取附近上下文
        for kw in ["保存草稿", "save", "draft"]:
            idx = html.lower().find(kw)
            if idx > 0:
                print(f"  '{kw}' 附近: ...{html[max(0,idx-30):idx+50]}...")
    else:
        print(f"\n❌ 数码之家没有存草稿功能")
    
    page.screenshot(path="/tmp/mydigit_draft_check.png", full_page=True)
    print(f"\n截图: /tmp/mydigit_draft_check.png")
    
    browser.close()
