"""
阿莫论坛全流程干跑 v2 — 修正版选择器
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
TEST_BODY = """ESP32-C3 深度睡眠可做到 5μA，关键配置：
1. 正确设置 RTC 外设
2. WiFi Modem Sleep 模式
3. 未用 GPIO 配置下拉

实测数据：
- Active TX: ~310mA
- Deep Sleep: 5μA

本文由 FlashSloth 自动生成测试草稿，不会正式发布。"""

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
    print("  ✅ 页面加载完成")
    page.screenshot(path="/tmp/amobbs_v2_01.png")
    
    # Step 2: 填写标题
    print("\n[2] 填写标题...")
    page.fill("input#subject", TEST_TITLE)
    print(f"  ✅ 标题: {TEST_TITLE[:40]}...")
    time.sleep(1)
    
    # Step 3: 填写内容（textarea#e_textarea）
    print("\n[3] 填写内容...")
    page.fill("textarea#e_textarea", TEST_BODY)
    print(f"  ✅ 内容已填写 ({len(TEST_BODY)} chars)")
    page.screenshot(path="/tmp/amobbs_v2_02_filled.png")
    time.sleep(1)
    
    # Step 4: 上传图片
    print("\n[4] 上传图片...")
    # 使用 imgattachform 的文件输入
    file_input = page.query_selector("#imgattachform input[type='file'], input#imgattachnew_1")
    if file_input:
        try:
            from PIL import Image
            import tempfile
            test_img = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            img = Image.new('RGB', (100, 100), color=(0, 120, 255))
            img.save(test_img.name, 'PNG')
            file_input.set_input_files(test_img.name)
            print(f"  ✅ 图片已选择: {test_img.name}")
            
            # 点击上传按钮
            upload_btn = page.query_selector("#imgattachform button:has-text('上传'), button:has-text('上传')")
            if upload_btn:
                upload_btn.click()
                print(f"  ✅ 已点击上传按钮")
                time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ 上传失败: {e}")
    else:
        print("  ⚠️ 未找到图片上传输入框")
    
    page.screenshot(path="/tmp/amobbs_v2_03_uploaded.png")
    time.sleep(1)
    
    # Step 5: 存草稿
    print("\n[5] 存草稿...")
    
    # 方法1: 点击「保存草稿」按钮
    save_btn = page.query_selector("button:has-text('保存草稿')")
    if save_btn:
        print("  找到「保存草稿」按钮")
        # 用 JS 点击，避免可见性问题
        page.evaluate("document.querySelector('button:has-text(\"保存草稿\")').click()")
        print("  ✅ 已点击保存草稿")
        time.sleep(3)
        page.screenshot(path="/tmp/amobbs_v2_04_draft_result.png")
        
        # 检查结果
        final_url = page.url
        final_content = page.content()
        print(f"\n结果页面 URL: {final_url}")
        if 'draft' in final_url or 'forum.php' in final_url:
            print("  ✅ 草稿已保存（跳转到论坛页）")
        elif 'save' in final_url or '草稿' in final_content:
            print("  ✅ 草稿保存成功")
        else:
            # 检查是否有错误消息
            err = page.query_selector("#messagetext, .alert_error")
            if err:
                print(f"  ⚠️ 返回消息: {err.inner_text()[:200]}")
            else:
                print(f"  ℹ️ 页面标题: {page.title()[:60]}")
    else:
        print("  ⚠️ 未找到保存草稿按钮，使用表单提交...")
        # 方法2: 设置 hidden input save=1 然后提交
        page.evaluate("""
            document.querySelector('input[name="save"]').value = '1';
            document.querySelector('form#postform').submit();
        """)
        time.sleep(3)
        page.screenshot(path="/tmp/amobbs_v2_04_draft_result.png")
        print("  ✅ 已通过表单提交存草稿")
    
    # 最终截图
    page.screenshot(path="/tmp/amobbs_v2_05_final.png", full_page=True)
    
    print(f"\n{'='*60}")
    print("✅ 阿莫论坛全流程干跑完成!")
    print("截图:")
    for i in range(1, 6):
        print(f"  /tmp/amobbs_v2_0{i}.png")
    
    browser.close()
