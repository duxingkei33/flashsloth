"""
阿莫论坛 (amobbs.com) — Playwright 深度探索
协议：2-5秒间隔 | 最多5次操作 | 遇封停 | 只读不写
"""
import json, time, sys, os, re, sqlite3

SITE = "https://www.amobbs.com"

# 从 DB 读 Cookie
db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), "flashsloth.db"))
cur = db.cursor()
cur.execute("SELECT config_json FROM platform_accounts WHERE id=1")
cfg = json.loads(cur.fetchone()[0])
db.close()
COOKIE_STR = cfg.get("cookie", "")
USERNAME = cfg.get("username", "duxingkei")
FID = cfg.get("fid", "")
SITE_URL = cfg.get("site_url", SITE)

# 用 FS venv
FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright

findings = {}
last_request_time = 0

def human_delay():
    global last_request_time
    now = time.time()
    if last_request_time > 0:
        elapsed = now - last_request_time
        if elapsed < 2:
            time.sleep(2 - elapsed + (time.time() % 2))
    delay = 2 + (time.time() % 3)
    time.sleep(delay)
    last_request_time = time.time()

def check_ban(page):
    body = page.content()[:500].lower()
    url = page.url.lower()
    title = page.title().lower()
    signals = ["418", "429", "403", "too many requests", "rate limit", "blocked", "captcha", "验证码", "拒绝访问", "安全验证"]
    for s in signals:
        if s in body or s in url or s in title:
            print(f"  ⛔ 反爬信号: '{s}' — 停止")
            return True
    return False

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
    for c in COOKIE_STR.split("; "):
        if "=" in c:
            k, v = c.split("=", 1)
            ctx.add_cookies([{"name": k.strip(), "value": v.strip(), "domain": ".amobbs.com", "path": "/"}])

    page = ctx.new_page()

    # ============= OP 1: 首页 =============
    print("[OP 1/5] 访问首页，检查登录状态")
    page.goto(f"{SITE}/forum.php", wait_until="networkidle", timeout=60000)
    human_delay()
    if check_ban(page): exit()
    
    page.screenshot(path="/tmp/amobbs_op1_home.png", full_page=True)
    
    username_el = page.query_selector(".vwmy, .z a[href*='space-uid'], #um .z a")
    print(f"  已登录: {username_el is not None}")
    if username_el:
        print(f"  用户名: {username_el.inner_text()}")
    
    # 版块列表
    forums = page.query_selector_all("h2 a[href*='fid=']")
    print(f"  版块数: {len(forums)}")
    forum_list = []
    for f in forums[:20]:
        name = f.inner_text().strip()
        href = f.get_attribute("href") or ""
        fid_m = re.search(r'fid=(\d+)', href)
        fid = fid_m.group(1) if fid_m else ""
        forum_list.append({"name": name, "fid": fid})
        print(f"    [{fid}] {name}")
    findings["forums"] = forum_list
    
    # 公告
    notice = page.query_selector("#announcement, .notice, #wp .notice")
    if notice:
        findings["notice"] = notice.inner_text()[:500]

    # ============= OP 2: 公告/版规页 =============
    print("\n[OP 2/5] 访问公告页")
    page.goto(f"{SITE}/forum.php?mod=announcement", wait_until="networkidle", timeout=60000)
    human_delay()
    if check_ban(page): exit()
    
    ann = page.query_selector(".mn, #annbody")
    if ann:
        text = ann.inner_text()[:1500]
        print(f"  公告: {text[:200]}...")
        findings["announcement"] = text
    page.screenshot(path="/tmp/amobbs_op2_announcement.png")

    # ============= OP 3: 访问一个版块（找版规） =============
    print("\n[OP 3/5] 访问版块，读取版规帖")
    # 用常用版块: 10061 (水坛) 或其他
    target_fid = "10061"  # 水坛—这是amobbs常见版块
    page.goto(f"{SITE}/forum.php?mod=forumdisplay&fid={target_fid}", wait_until="networkidle", timeout=60000)
    human_delay()
    if check_ban(page): exit()
    
    rules_el = page.query_selector("#forumrules, .rules, .bn")
    if rules_el:
        text = rules_el.inner_text()
        print(f"  版规: {text[:500]}")
        findings["forum_rules"] = text[:2000]
    
    # 找置顶帖
    sticky = page.query_selector_all("th.common a.xst")
    print(f"\n  帖子列表: {len(sticky)} 个")
    for t in sticky[:15]:
        print(f"    {t.inner_text()[:60]}")
    
    page.screenshot(path="/tmp/amobbs_op3_forum.png")

    # ============= OP 4: 发帖页 =============
    print("\n[OP 4/5] 访问发帖页，检查编辑器+上传限制")
    page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid={target_fid}", wait_until="networkidle", timeout=60000)
    human_delay()
    if check_ban(page): exit()
    
    # 权限检查
    err = page.query_selector("#messagetext, .alert_error")
    if err:
        print(f"  ⚠️ 无发帖权限: {err.inner_text()[:200]}")
        findings["post_permission"] = f"❌ {err.inner_text()[:200]}"
    else:
        print("  ✅ 有发帖权限")
        findings["post_permission"] = "✅ 有"
    
    # 标题
    title_input = page.query_selector("input#subject")
    if title_input:
        maxlen = title_input.get_attribute("maxlength")
        print(f"  标题 maxlength: {maxlen}")
        findings["title_maxlength"] = int(maxlen) if maxlen else 80
    
    # 编辑器
    textarea = page.query_selector("textarea#message, textarea#fastpostmessage")
    if textarea:
        print(f"  textarea 编辑器 ✅")
        findings["editor"] = {"type": "textarea"}
    else:
        iframe = page.query_selector("iframe[id^='e_iframe']")
        if iframe:
            print(f"  富文本 iframe 编辑器 ✅")
            findings["editor"] = {"type": "richtext_iframe"}
    
    # 上传区域
    upload = page.query_selector("#attachnotice_img, .upload_area, #uploadapp, a[href*='upload']")
    if upload:
        print(f"  上传区域: 存在 ✅")
    
    # 上传限制 — 解析页面源码
    html = page.content()
    
    # 大小限制
    sizes = re.findall(r'(?:大小|尺寸|上限|最大)[：:\s]*[^。\n]{0,50}(?:\d+\.?\d*\s*(?:KB|MB|GB|K|M))', html)
    if sizes:
        print(f"  大小限制: {sizes[:3]}")
        findings["size_limits"] = sizes[:3]
    
    # 每日限制
    daily = re.findall(r'(?:每天|每日|今日)[^。\n]{0,50}(?:\d+)[^。\n]{0,50}(?:张|个|次|MB|KB)', html)
    if daily:
        print(f"  每日限制: {daily[:3]}")
        findings["daily_limits"] = daily[:3]
    
    # 扩展名
    exts = re.findall(r"extensions\s*=\s*'([^']+)'", html)
    if exts:
        print(f"  允许扩展名: {exts[0]}")
        findings["extensions"] = exts[0]
    else:
        # 从 accept 属性
        accepts = re.findall(r'accept="([^"]+)"', html)
        for a in accepts:
            if 'image' in a or '.jpg' in a:
                print(f"  accept: {a[:100]}")
                findings["accept"] = a[:200]
    
    # uid / hash
    uids = re.findall(r'uid["\']?\s*[:=]\s*["\']?(\d+)["\']?', html)
    hashes = re.findall(r'hash["\']?\s*[:=]\s*["\']?([a-f0-9]+)["\']?', html)
    if uids:
        print(f"  uid: {uids[0]}")
        findings["uid"] = uids[0]
    if hashes:
        print(f"  hash: {hashes[0]}")
        findings["hash"] = hashes[0]
    
    page.screenshot(path="/tmp/amobbs_op4_editor.png", full_page=True)

    # ============= OP 5: 个人中心 =============
    print("\n[OP 5/5] 个人中心 — 确认登录状态")
    page.goto(f"{SITE}/home.php?mod=space&do=profile", wait_until="networkidle", timeout=60000)
    human_delay()
    if check_ban(page): exit()
    
    profile = page.query_selector(".profile, .ct, #profile")
    if profile:
        text = profile.inner_text()[:500]
        print(f"  个人信息: {text[:200]}...")
        findings["profile"] = text[:500]
    page.screenshot(path="/tmp/amobbs_op5_profile.png")

    # ============= 汇总 =============
    print(f"\n{'='*60}")
    print(f"探索完成！共 5 次操作")
    print(f"发现 {len(findings)} 条信息")
    
    browser.close()
    
    # 保存
    output = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "findings": {k: str(v) if not isinstance(v, (str, list, dict)) else v for k, v in findings.items()}}
    out_path = "/tmp/amobbs_exploration.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"结果保存至 {out_path}")
    
    print("\n发现摘要:")
    for k, v in findings.items():
        if isinstance(v, str) and len(v) > 100:
            print(f"  📌 {k}: {v[:100]}...")
        else:
            print(f"  📌 {k}: {v}")
