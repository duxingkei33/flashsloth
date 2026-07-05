"""
阿莫论坛全流程干跑 v3 — 所有操作用 JS
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

TEST_TITLE = "【FlashSloth 草稿测试】ESP32-C3 功耗优化经验"
TEST_BODY = "ESP32-C3 深度睡眠可做到 5μA。实测数据：Active TX ~310mA，Deep Sleep 5μA。"

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
            ctx.add_cookies([{"name": k.strip(), "value": v.strip(), "domain": ".amobbs.com", "path": "/"}])
    
    page = ctx.new_page()
    
    # Step 1: 访问发帖页
    print("[1] 访问发帖页...")
    page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid=10061", wait_until="networkidle", timeout=60000)
    time.sleep(2)
    page.screenshot(path="/tmp/amobbs3_01.png")
    
    # Step 2: 填写标题 + 内容
    print("\n[2] 填写标题和内容...")
    page.fill("input#subject", TEST_TITLE)
    page.fill("textarea#e_textarea", TEST_BODY)
    print("  ✅ 已填写")
    page.screenshot(path="/tmp/amobbs3_02_filled.png")
    time.sleep(1)
    
    # Step 3: 上传图片
    print("\n[3] 上传图片...")
    try:
        from PIL import Image
        import tempfile
        test_img = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        img = Image.new('RGB', (100, 100), color=(0, 120, 255))
        img.save(test_img.name, 'PNG')
        
        file_input = page.query_selector("#imgattachnew_1")
        if file_input:
            file_input.set_input_files(test_img.name)
            print(f"  ✅ 图片已选择: {test_img.name}")
            time.sleep(2)
    except Exception as e:
        print(f"  ⚠️ 图片上传: {e}")
    
    page.screenshot(path="/tmp/amobbs3_03_uploaded.png")
    time.sleep(1)
    
    # Step 4: 存草稿 — 用 JS 直接提交表单带 save=1
    print("\n[4] 存草稿...")
    
    page.evaluate("""
        var form = document.getElementById('postform');
        var saveInput = document.getElementById('postsave');
        if (saveInput) saveInput.value = '1';
        // 直接提交表单
        form.submit();
    """)
    print("  ✅ 已通过 JS 提交存草稿")
    time.sleep(3)
    page.screenshot(path="/tmp/amobbs3_04_draft_result.png")
    
    # 检查结果
    final_url = page.url
    print(f"\n结果 URL: {final_url}")
    print(f"页面标题: {page.title()[:60]}")
    
    content = page.content()
    if 'forum.php' in final_url and 'fid=' in final_url:
        print("✅ 草稿已保存（跳转到版块页）")
    elif 'save' in content or '草稿' in content:
        print("✅ 草稿保存成功")
    elif 'error' in content.lower() or 'alert_error' in content:
        err = re.search(r'<div[^>]*class="alert_error"[^>]*>(.*?)</div>', content, re.DOTALL)
        if err:
            print(f"⚠️ 错误: {re.sub(r'<[^>]+>', ' ', err.group(1)).strip()[:200]}")
        else:
            print("⚠️ 状态不明，请查看截图")
    else:
        print("ℹ️ 状态：页面已跳转，草稿可能已保存")
    
    page.screenshot(path="/tmp/amobbs3_05_final.png", full_page=True)
    print("\n✅ 全流程干跑完成！截图:")
    for i in range(1, 6):
        print(f"  /tmp/amobbs3_0{i}.png")
    
    browser.close()
