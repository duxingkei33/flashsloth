"""
立创开源硬件平台 (oshwhub.com) — Playwright 深度探索
需要先获取 Cookie（API 签到已有，但编辑器需浏览器）
"""
import json, time, sys, os, re, sqlite3

SITE = "https://oshwhub.com"

# 从 DB 读配置
db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "flashsloth.db"))
cur = db.cursor()
cur.execute("SELECT config_json FROM platform_accounts WHERE id=5")
cfg = json.loads(cur.fetchone()[0])
db.close()
COOKIE_STR = cfg.get("cookie", "")
USERNAME = cfg.get("username", "17354703489")

FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright

findings = {}

def human_delay():
    time.sleep(2 + (time.time() % 3))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled', '--no-sandbox'])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        viewport={"width": 1920, "height": 1080}, locale="zh-CN"
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    """)
    # OSHWHub Cookie 是 JSESSIONID 格式
    for c in COOKIE_STR.split("; "):
        if "=" in c:
            k, v = c.split("=", 1)
            ctx.add_cookies([{"name": k.strip(), "value": v.strip(), "domain": ".oshwhub.com", "path": "/"}])

    page = ctx.new_page()

    # OP 1: 首页
    print("[OP 1/5] 访问首页，检查登录状态...")
    page.goto(f"{SITE}/", wait_until="networkidle", timeout=60000)
    human_delay()
    
    content = page.content()
    title = page.title()
    print(f"  标题: {title}")
    
    # 检查登录 — OSHWHub 登录后应有用户信息
    username_match = USERNAME in content
    login_link = "登录" in content[:5000]
    print(f"  用户名可见: {username_match}")
    print(f"  有登录按钮: {login_link}")
    
    page.screenshot(path="/tmp/oshwhub_op1_home.png", full_page=True)
    
    # 检查页面是否有 API 文档或发布入口
    api_links = page.query_selector_all("a[href*='api'], a[href*='project'], a[href*='doc'], a[href*='create']")
    print(f"\n  相关链接:")
    for a in api_links[:10]:
        href = a.get_attribute("href") or ""
        text = a.inner_text().strip()
        if text:
            print(f"    {text} → {href[:60]}")

    # OP 2: 个人中心
    print("\n[OP 2/5] 访问个人中心...")
    page.goto(f"{SITE}/user", wait_until="networkidle", timeout=60000)
    human_delay()
    print(f"  标题: {page.title()[:60]}")
    print(f"  URL: {page.url}")
    page.screenshot(path="/tmp/oshwhub_op2_user.png", full_page=True)

    # OP 3: 探索项目/文档页面 — 找发布入口
    print("\n[OP 3/5] 找发布/创建项目入口...")
    # 尝试几个常见路径
    for path in ["/project/create", "/projects/new", "/doc/create", "/docs/new", "/write", "/editor", "/post/new"]:
        try:
            resp = page.goto(f"{SITE}{path}", wait_until="networkidle", timeout=15000)
            if resp and resp.status < 400:
                print(f"  ✅ {path}: HTTP {resp.status} — {page.title()[:40]}")
            else:
                print(f"  ⚠️ {path}: HTTP {resp.status if resp else 'N/A'}")
            human_delay()
        except:
            print(f"  ❌ {path}: 超时/错误")
    
    page.screenshot(path="/tmp/oshwhub_op3_explore.png")

    # OP 4: 看项目页结构
    print("\n[OP 4/5] 查看现有项目页结构...")
    page.goto(f"{SITE}/", wait_until="networkidle", timeout=30000)
    human_delay()
    
    # 找项目卡片/链接
    project_links = page.query_selector_all("a[href*='/project/'], a[href*='/doc/']")
    print(f"  项目链接: {len(project_links)} 个")
    for pl in project_links[:5]:
        href = pl.get_attribute("href") or ""
        text = pl.inner_text().strip()[:60]
        print(f"    {text} → {href}")
    
    page.screenshot(path="/tmp/oshwhub_op4_projects.png")

    # OP 5: 查看编辑页面（如果有）
    print("\n[OP 5/5] 尝试查看 API/帮助文档...")
    for path in ["/api/v1/docs", "/help", "/about", "/faq"]:
        try:
            resp = page.goto(f"{SITE}{path}", wait_until="networkidle", timeout=10000)
            if resp and resp.status < 400:
                print(f"  ✅ {path}: {page.title()[:50]}")
            human_delay()
        except:
            pass
    
    page.screenshot(path="/tmp/oshwhub_op5_api.png")

    print(f"\n{'='*60}")
    print(f"探索完成！")

    browser.close()
