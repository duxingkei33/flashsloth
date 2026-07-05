"""
诊断 amobbs 发帖页面的真实结构
"""
import json, time, sys, os, re, sqlite3

SITE = "https://www.amobbs.com"
db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "flashsloth.db"))
cur = db.cursor()
cur.execute("SELECT config_json FROM platform_accounts WHERE id=1")
cfg = json.loads(cur.fetchone()[0])
db.close()
COOKIE_STR = cfg.get("cookie", "")

FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent="Mozilla/5.0", viewport={"width": 1920, "height": 1080})
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    for c in COOKIE_STR.split("; "):
        if "=" in c:
            k, v = c.split("=", 1)
            ctx.add_cookies([{"name": k.strip(), "value": v.strip(), "domain": ".amobbs.com", "path": "/"}])
    
    page = ctx.new_page()
    page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid=10061", wait_until="networkidle", timeout=60000)
    time.sleep(2)
    
    # 分析页面元素
    print("=== 所有 input 元素 ===")
    inputs = page.query_selector_all("input, textarea, select")
    for el in inputs:
        tag = el.evaluate("el => el.tagName")
        name = el.get_attribute("name") or "(no name)"
        id_ = el.get_attribute("id") or "(no id)"
        type_ = el.get_attribute("type") or ""
        placeholder = el.get_attribute("placeholder") or ""
        if name and name != "(no name)":
            print(f"  <{tag}> name={name} id={id_} type={type_} placeholder={placeholder[:30]}")
    
    print("\n=== 所有 form ===")
    forms = page.query_selector_all("form")
    for f in forms:
        fid = f.get_attribute("id") or "(no id)"
        action = f.get_attribute("action") or "(no action)"
        method = f.get_attribute("method") or "get"
        print(f"  <form> id={fid} method={method} action={action[:80]}")
    
    print("\n=== 所有 iframe ===")
    iframes = page.query_selector_all("iframe")
    for ifr in iframes:
        fid = ifr.get_attribute("id") or "(no id)"
        src = ifr.get_attribute("src") or ""
        print(f"  <iframe> id={fid} src={src[:80]}")
    
    print("\n=== 所有 button ===")
    buttons = page.query_selector_all("button, input[type='submit']")
    for btn in buttons:
        tag = btn.evaluate("el => el.tagName")
        text = btn.inner_text() or btn.get_attribute("value") or ""
        name = btn.get_attribute("name") or ""
        if text or name:
            print(f"  <{tag}> name={name} text={text[:40]}")
    
    print("\n=== formhash ===")
    html = page.content()
    fh = re.search(r'name="formhash"[^>]+value="([^"]+)"', html)
    if fh:
        print(f"  formhash: {fh.group(1)}")
    
    print("\n=== 上传相关 ===")
    for pat in [r'extensions\s*=\s*\'([^\']+)\'', r'uid["\']?\s*[:=]\s*["\']?(\d+)', r'hash["\']?\s*[:=]\s*["\']?([a-f0-9]+)']:
        m = re.search(pat, html)
        if m:
            print(f"  {pat[:30]}: {m.group(1)}")
    
    print("\n=== 页面标题 ===")
    print(f"  {page.title()}")
    
    page.screenshot(path="/tmp/amobbs_diagnose.png", full_page=True)
    print("\n截图: /tmp/amobbs_diagnose.png")
    
    # 保存完整 HTML 用于分析
    with open("/tmp/amobbs_post_page.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 保存至 /tmp/amobbs_post_page.html")
    
    browser.close()
