#!/usr/bin/env python3
"""掘金 (juejin.cn) 平台预探索脚本 - 无凭证模式"""
import json, os, re, sys, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flashsloth.core.explorer import can_explore, mark_explored

SITE_URL = "https://juejin.cn"
DOMAIN = "juejin.cn"
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "platform_reports")
SCREENSHOTS_DIR = os.path.join(REPORTS_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

result = {
    "platform": "juejin",
    "platform_domain": DOMAIN,
    "explored_at": datetime.utcnow().isoformat(),
    "explored_with_login": False,
    "needs_credentials": True,
    "site_url": SITE_URL,
    "login_page": {},
    "editor_access": {},
    "api_endpoints": [],
    "publisher_status": "exists_but_needs_rewrite",  # requests-based, needs Playwright
    "publisher_file": "plugins/publisher_juejin.py",
}

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed. Install with: pip install playwright && playwright install chromium")
    sys.exit(1)

def safe_text(page, selector, default=""):
    try:
        el = page.query_selector(selector)
        return el.inner_text()[:100] if el else default
    except:
        return default

def check_ban(page):
    signals = ["418", "429", "403", "too many requests", "rate limit",
               "blocked", "captcha", "验证码", "拒绝访问", "频繁", "安全验证"]
    body = page.content()[:2000].lower()
    url = page.url.lower()
    for s in signals:
        if s in body or s in url:
            return True
    return False

print("=" * 60)
print("🚀 掘金平台预探索 - 无凭证模式")
print(f"  时间: {result['explored_at']}")
print("=" * 60)

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN",
    )
    ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    """)

    # ── Step 1: Visit login page ──
    print("\n📌 Step 1: 登录页探索")
    page = ctx.new_page()
    login_url = "https://juejin.cn/"

    # Intercept API calls
    api_urls = set()
    def handle_response(response):
        url = response.url
        if "juejin.cn" in url and ("api" in url or "/v1/" in url or "/v2/" in url or "/v3/" in url):
            api_urls.add(url[:250])

    page.on("response", handle_response)
    page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)

    if check_ban(page):
        print("⚠️ 检测到封禁信号！")
        result["login_page"]["blocked"] = True
        page.close()
        browser.close()
        json.dump(result, open(os.path.join(SCREENSHOTS_DIR, "..", "juejin_exploration_report.json"), "w"), indent=2, ensure_ascii=False)
        print("结果已保存，但由于封禁信号提前终止。")
        sys.exit(0)

    # Screenshot
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, "juejin_login_page.png"), full_page=True)
    print("  ✅ 登录页截图已保存")

    # Analyze login page
    html = page.content()

    # Detect login methods
    methods = []
    result["login_page"]["title"] = page.title()
    result["login_page"]["url"] = page.url

    # Check for input types
    inputs = page.query_selector_all("input")
    input_info = []
    for el in inputs:
        if el.is_visible():
            info = {
                "type": el.get_attribute("type") or "",
                "name": el.get_attribute("name") or "",
                "placeholder": el.get_attribute("placeholder") or "",
                "id": el.get_attribute("id") or "",
            }
            input_info.append(info)
    result["login_page"]["inputs"] = input_info
    print(f"  📋 检测到 {len(input_info)} 个可见 input")

    buttons = page.query_selector_all("button")
    button_texts = []
    for el in buttons:
        if el.is_visible():
            txt = (el.inner_text() or "").strip()
            if txt:
                button_texts.append(txt[:60])
    result["login_page"]["buttons"] = button_texts
    print(f"  📋 检测到 {len(button_texts)} 个可见按钮: {button_texts[:10]}")

    # Detect specific login methods
    has_password = bool(re.search(r'type="password"', html))
    has_phone = bool(re.search(r'phone|手机号|手机|type="tel"', html[:10000]))
    has_qrcode = bool(re.search(r'qrcode|扫码|二维码', html[:10000]))
    has_code_btn = bool(re.search(r'验证码|获取验证码|send.*code', html[:10000]))

    print(f"  🔍 密码输入: {'✅' if has_password else '❌'}")
    print(f"  🔍 手机号输入: {'✅' if has_phone else '❌'}")
    print(f"  🔍 验证码按钮: {'✅' if has_code_btn else '❌'}")
    print(f"  🔍 二维码登录: {'✅' if has_qrcode else '❌'}")

    result["login_page"]["has_password"] = has_password
    result["login_page"]["has_phone"] = has_phone
    result["login_page"]["has_code_button"] = has_code_btn
    result["login_page"]["has_qrcode"] = has_qrcode

    # Try to find login tab buttons to understand login method switching
    # Juejin has multiple auth methods
    login_tabs = page.query_selector_all("button, div[role='tab'], .tab, [class*='tab'], [class*='Tab'], [class*='login-']")
    login_tab_texts = []
    for el in login_tabs:
        txt = (el.inner_text() or "").strip()
        if txt and len(txt) < 20 and txt not in ["登录", "注册"]:
            login_tab_texts.append(txt)

    # Look for tab switching elements more broadly
    auth_switches = page.query_selector_all(".auth-switch, [class*='switch'], [class*='Switch'], .login-type, [class*='loginType']")
    switch_texts = []
    for el in auth_switches:
        txt = (el.inner_text() or "").strip()
        if txt and len(txt) < 30:
            switch_texts.append(txt)

    result["login_page"]["login_tabs"] = list(set(login_tab_texts + switch_texts))
    print(f"  📋 登录 Tab/切换: {result['login_page']['login_tabs']}")

    page.close()
    time.sleep(2)

    # ── Step 2: Check editor URL ──
    print("\n📌 Step 2: 编辑器 URL 检测")
    page2 = ctx.new_page()
    writer_url = "https://juejin.cn/editor/drafts/new"

    page2.on("response", handle_response)
    page2.goto(writer_url, wait_until="domcontentloaded", timeout=30000)
    page2.wait_for_timeout(5000)

    redirected = "passport" in page2.url.lower() or "login" in page2.url.lower() or "signin" in page2.url.lower()
    result["editor_access"] = {
        "url": writer_url,
        "final_url": page2.url,
        "redirected_to_login": redirected,
        "status_code": 401 if redirected else 200,
    }

    print(f"  编辑器 URL: {writer_url}")
    print(f"  最终 URL: {page2.url}")
    print(f"  被重定向到登录: {'✅ (需要登录才能编辑)' if redirected else '❌ (编辑器可直接访问)'}")

    if not redirected:
        page2.screenshot(path=os.path.join(SCREENSHOTS_DIR, "juejin_editor.png"), full_page=True)
        # Analyze editor structure
        editor_inputs = page2.query_selector_all("input, textarea, select, [contenteditable]")
        editor_info = []
        for el in editor_inputs:
            if el.is_visible():
                info = {
                    "tag": el.evaluate("el => el.tagName"),
                    "type": el.get_attribute("type") or "",
                    "placeholder": el.get_attribute("placeholder") or "",
                    "id": el.get_attribute("id") or "",
                    "contenteditable": el.get_attribute("contenteditable") or "",
                }
                editor_info.append(info)
        result["editor_access"]["editor_fields"] = editor_info
        print(f"  📋 编辑器字段: {len(editor_info)} 个")

    page2.close()
    time.sleep(2)

    # ── Step 3: Browse homepage for API discovery ──
    print("\n📌 Step 3: API 端点发现")
    page3 = ctx.new_page()
    page3.on("response", handle_response)
    page3.goto(SITE_URL, wait_until="domcontentloaded", timeout=30000)
    page3.wait_for_timeout(5000)

    if check_ban(page3):
        print("⚠️ 主页访问被限制")
    else:
        page3.screenshot(path=os.path.join(SCREENSHOTS_DIR, "juejin_homepage.png"), full_page=True)
        print("  ✅ 首页截图已保存")

    page3.close()

    # Collect API endpoints from all page loads
    result["api_endpoints"] = sorted(list(api_urls))[:50]
    print(f"  📡 发现 API 端点: {len(result['api_endpoints'])} 个")
    for url in sorted(list(api_urls))[:15]:
        print(f"    - {url[:150]}")

    # ── Step 4: Check post/article reading (public) ──
    print("\n📌 Step 4: 公开文章阅读")
    page4 = ctx.new_page()
    post_url = "https://juejin.cn/post/6844903506986803213"  # classic juejin post
    try:
        page4.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        page4.wait_for_timeout(4000)
        post_title = safe_text(page4, "h1.article-title, .article-title, h1")
        post_body = safe_text(page4, ".article-content, .markdown-body, .article-body, .content-wrapper, main")
        result["public_post_access"] = {
            "url": post_url,
            "accessible": "文章" in page4.content()[:3000] or "掘金" in page4.content()[:500],
            "title": post_title,
            "body_preview": post_body[:200] if post_body else "",
        }
        print(f"  公开文章可读: {'✅' if result['public_post_access']['accessible'] else '⚠️'}")
        if post_title:
            print(f"  标题: {post_title}")
    except Exception as e:
        result["public_post_access"] = {"url": post_url, "accessible": False, "error": str(e)}
        print(f"  ⚠️ 文章读取异常: {e}")

    page4.close()

    browser.close()

# ── Save results ──
print("\n📌 Step 5: 保存结果")

# 1. Update platform_config in DB
try:
    import sqlite3
    db_path = os.path.join(os.path.dirname(__file__), "..", "flashsloth.db")
    conn = sqlite3.connect(db_path)
    
    config_json = {
        "platform": "juejin",
        "explored_with_login": False,
        "needs_credentials": True,
        "recommended_login": "qrcode",
        "credentials_required": ["phone", "password"],
        "publisher_status": "exists_but_needs_rewrite",
        "login_methods": [
            {"method": "password", "label": "账号密码登录", "priority": 1, "note": "需处理验证码"},
            {"method": "phone", "label": "手机验证码登录", "priority": 1},
            {"method": "qrcode", "label": "📱 扫码登录", "priority": 2},
            {"method": "cookie", "label": "Cookie粘贴（备选）", "priority": 99},
        ],
        "capabilities": {
            "login": ["password", "phone", "qrcode", "cookie"],
            "publish": True,
            "publish_mode": "requests_api",  # currently requests-based
            "upload_image": True,
            "save_draft": True,
            "sign_in": False,
            "fetch_posts": True,  # public reading
        },
        "login_page_findings": {
            "has_password": has_password,
            "has_phone": has_phone,
            "has_code_button": has_code_btn,
            "has_qrcode": has_qrcode,
        },
        "editor_redirected": redirected,
    }
    
    conn.execute(
        "INSERT OR REPLACE INTO platform_config (platform, platform_domain, config_json, updated_at) VALUES (?, ?, ?, datetime('now'))",
        ("juejin", DOMAIN, json.dumps(config_json, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
    print("  ✅ platform_config 已更新")
except Exception as e:
    print(f"  ⚠️ 更新 platform_config 失败: {e}")

# 2. Save exploration report JSON
report_json_path = os.path.join(REPORTS_DIR, "juejin_exploration_report.json")
existing = {}
if os.path.exists(report_json_path):
    try:
        existing = json.load(open(report_json_path))
    except:
        pass
existing.update(result)
json.dump(existing, open(report_json_path, "w"), indent=2, ensure_ascii=False)
print(f"  ✅ 探索报告 JSON 已保存: {report_json_path}")

# 3. Mark explored in cooldown
try:
    mark_explored(DOMAIN)
    print("  ✅ 探索冷却已记录")
except Exception as e:
    print(f"  ⚠️ 记录冷却失败: {e}")

# ── Summary ──
print("\n" + "=" * 60)
print("📊 探索摘要")
print("=" * 60)
print(f"  平台: 掘金 (juejin.cn)")
print(f"  登录方式: 密码/手机验证码/扫码/Cookie")
print(f"  编辑器需要登录: {'✅' if redirected else '❌'}")
print(f"  API 端点发现: {len(result['api_endpoints'])} 个")
print(f"  Publisher 状态: 已存在但使用 requests（需重写为 Playwright）")
print(f"  公开文章可读: {'✅' if result.get('public_post_access', {}).get('accessible') else '⚠️'}")
print(f"  需要凭证: ✅ (无有效凭证)")
print("=" * 60)
