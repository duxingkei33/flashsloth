"""
立创开源硬件平台 — 深度探索 /project/create 和 /write
"""
import json, time, sys, os, re, sqlite3

SITE = "https://oshwhub.com"
db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "flashsloth.db"))
cur = db.cursor()
cur.execute("SELECT config_json FROM platform_accounts WHERE id=5")
cfg = json.loads(cur.fetchone()[0])
db.close()
COOKIE_STR = cfg.get("cookie", "")
USERNAME = cfg.get("username", "17354703489")
PASSWORD = cfg.get("password", "")

FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        viewport={"width": 1920, "height": 1080}, locale="zh-CN"
    )
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    for c in COOKIE_STR.split("; "):
        if "=" in c:
            k, v = c.split("=", 1)
            ctx.add_cookies([{"name": k.strip(), "value": v.strip(), "domain": ".oshwhub.com", "path": "/"}])

    page = ctx.new_page()

    # 1. /write 页面（文章编辑器）
    print("=" * 60)
    print("[探索 A] /write — 文章编辑器")
    page.goto(f"{SITE}/write", wait_until="networkidle", timeout=60000)
    time.sleep(3)
    print(f"  URL: {page.url}")
    print(f"  标题: {page.title()[:60]}")
    page.screenshot(path="/tmp/oshwhub_a_write.png", full_page=True)
    
    # 检查登录状态
    if "login" in page.url.lower() or "signin" in page.url.lower():
        print("  ⚠️ 未登录，被重定向到登录页")
    else:
        print("  ✅ 已登录，可访问编辑器")
        
        # 分析页面元素
        inputs = page.query_selector_all("input:not([type='hidden']), textarea, [contenteditable]")
        print(f"  输入框数: {len(inputs)}")
        for inp in inputs[:10]:
            tag = inp.evaluate("el => el.tagName")
            name = inp.get_attribute("name") or "(no name)"
            id_ = inp.get_attribute("id") or "(no id)"
            placeholder = inp.get_attribute("placeholder") or ""
            print(f"    <{tag}> name={name} id={id_} placeholder={placeholder[:30]}")
        
        # 找编辑器主体
        editor = page.query_selector("[contenteditable], .editor, .ql-editor, .CodeMirror, textarea")
        if editor:
            print(f"  ✅ 发现编辑器")
        
        # 找提交/发布按钮
        buttons = page.query_selector_all("button, input[type='submit']")
        for btn in buttons:
            text = (btn.inner_text() or btn.get_attribute("value") or "").strip()
            if text and len(text) < 30:
                print(f"  按钮: {text}")
        
        html = page.content()
        # 检查是否有 Markdown 编辑器特征
        if "markdown" in html.lower() or "codemirror" in html.lower():
            print("  📝 Markdown 编辑器")
        if "quill" in html.lower() or "ql-editor" in html.lower():
            print("  📝 Quill 富文本编辑器")

    # 2. /project/create（硬件项目创建）
    print("\n" + "=" * 60)
    print("[探索 B] /project/create — 新建工程项目")
    page.goto(f"{SITE}/project/create", wait_until="networkidle", timeout=60000)
    time.sleep(3)
    print(f"  URL: {page.url}")
    print(f"  标题: {page.title()[:60]}")
    page.screenshot(path="/tmp/oshwhub_b_project_create.png", full_page=True)
    
    if "login" not in page.url.lower():
        # 分析页面
        inputs = page.query_selector_all("input:not([type='hidden']), textarea, select")
        for inp in inputs[:15]:
            tag = inp.evaluate("el => el.tagName")
            name = inp.get_attribute("name") or "(no name)"
            id_ = inp.get_attribute("id") or "(no id)"
            placeholder = inp.get_attribute("placeholder") or ""
            print(f"    <{tag}> name={name} id={id_} placeholder={placeholder[:30]}")
        
        buttons = page.query_selector_all("button, input[type='submit']")
        for btn in buttons:
            text = (btn.inner_text() or btn.get_attribute("value") or "").strip()
            if text and len(text) < 30:
                print(f"  按钮: {text}")

    # 3. 查看现有项目详情页（了解附件结构）
    print("\n" + "=" * 60)
    print("[探索 C] 现有项目页 — 了解附件/图片结构")
    # 取一个首页的项目链接
    page.goto(f"{SITE}/", wait_until="networkidle", timeout=30000)
    time.sleep(2)
    
    first_project = page.query_selector("a[href*='/project/']")
    if first_project:
        href = first_project.get_attribute("href") or ""
        if not href.startswith("http"):
            href = f"{SITE}{href}"
        print(f"  访问: {href}")
        page.goto(href, wait_until="networkidle", timeout=60000)
        time.sleep(2)
        print(f"  标题: {page.title()[:60]}")
        
        # 检查附件/图片
        images = page.query_selector_all("img[src*='attachment'], img[src*='upload'], .project-content img")
        print(f"  内容图片: {len(images)} 张")
        
        # 检查附件下载链接
        attachments = page.query_selector_all("a[href*='download'], a[href*='attachment'], .file-list a")
        print(f"  附件: {len(attachments)} 个")
        for a in attachments[:5]:
            print(f"    {a.inner_text()[:40]} → {a.get_attribute('href')[:60]}")
        
        page.screenshot(path="/tmp/oshwhub_c_project_detail.png", full_page=True)

    # 4. API 文档检查
    print("\n" + "=" * 60)
    print("[探索 D] OSHWHub API 端点")
    try:
        import requests
        # OSHWHub 的 API 端点
        api_endpoints = [
            ("GET", "https://oshwhub.com/api/v1/user/info"),
            ("POST", "https://oshwhub.com/api/v1/project/create"),
            ("GET", "https://oshwhub.com/api/v1/project/list"),
        ]
        for method, url in api_endpoints[:3]:
            if method == "GET":
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                print(f"  {method} {url}: HTTP {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    print(f"    响应: {str(data)[:200]}")
    except Exception as e:
        print(f"  API 检查: {e}")

    browser.close()
