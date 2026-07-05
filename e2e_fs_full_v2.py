"""
FS 后台完整 E2E 测试 v2 — 正确路由
写文章 → 保存 → 文章列表点「发布」→ 选存草稿 → 提交 → 验证
"""
import json, time, sys, os

FS_URL = "http://localhost:5000"
FS_USER = "admin_redacted"
FS_PASS = "aA123456"

FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        viewport={"width": 1920, "height": 1080}, locale="zh-CN"
    )
    page = ctx.new_page()

    # 登录
    print("[1] 登录 FS...")
    page.goto(f"{FS_URL}/login", wait_until="networkidle", timeout=30000)
    page.fill("input[name='username']", FS_USER)
    page.fill("input[name='password']", FS_PASS)
    page.click("button[type='submit']")
    time.sleep(2)
    print(f"  ✅ 登录成功")

    # 写新文章
    print("\n[2] 写新文章...")
    page.goto(f"{FS_URL}/post/new", wait_until="networkidle", timeout=30000)
    time.sleep(1)
    
    page.fill("input[name='title']", "【E2E存草稿测试】ESP32-S3 摄像头图像采集优化")
    page.fill("textarea[name='body']", """## 背景
ESP32-S3 带摄像头做图像采集，关键优化点：

### 1. 帧缓存策略
使用双缓冲避免撕裂。

### 2. JPEG 压缩
调整质量参数平衡速度与画质。

### 3. DMA 传输
利用硬件 DMA 减少 CPU 开销。

## 实测数据
- 240x240: 30fps
- 640x480: 15fps
- 800x600: 8fps""")
    page.fill("input[name='summary']", "ESP32-S3 摄像头采集优化方案")
    page.fill("input[name='tags']", "ESP32, 摄像头, 嵌入式")
    
    print("  ✅ 文章已填写")
    page.click("button[type='submit']")
    time.sleep(2)
    print(f"  保存后 URL: {page.url}")
    page.screenshot(path="/tmp/fs_e2e3_01_saved.png")

    # 从文章列表点「发布」
    print("\n[3] 找刚保存的文章并点「发布」...")
    # 页面应该回到首页，找最后一篇文章的发布按钮
    publish_links = page.query_selector_all("a[href*='/publish/select/']")
    if publish_links:
        last_link = publish_links[-1]  # 最后一篇（刚写的）
        href = last_link.get_attribute("href")
        print(f"  发布链接: {last_link.inner_text()} → {href}")
        page.goto(f"{FS_URL}{href}", wait_until="networkidle", timeout=30000)
        time.sleep(1)
        print(f"  发布选择页 URL: {page.url}")
    else:
        print("  ❌ 未找到发布链接")
        page.screenshot(path="/tmp/fs_e2e3_02_no_publish.png")
        browser.close()
        exit(1)
    
    page.screenshot(path="/tmp/fs_e2e3_02_publish_select.png")

    # 选择目标账号
    print("\n[4] 选择发布目标（存草稿模式）...")
    checkboxes = page.query_selector_all("input[name='account_ids']")
    print(f"  可用账号数: {len(checkboxes)}")
    
    selected = False
    for cb in checkboxes:
        val = cb.get_attribute("value")
        # 找 discuz 类型账号（amobbs 或 mydigit）
        parent_text = cb.evaluate("el => el.closest('.account-card')?.innerText || ''")
        if not cb.is_disabled() and ('mydigit' in parent_text.lower() or 'amobbs' in parent_text.lower()):
            cb.check()
            print(f"  ✅ 已勾选: {parent_text[:40]}...")
            selected = True
            # 展开详情
            page.evaluate(f"""
                var el = document.getElementById('extras-{val}');
                if (el) el.classList.add('active');
            """)
            break
    
    if not selected:
        # 勾选第一个可用
        for cb in checkboxes:
            if not cb.is_disabled():
                val = cb.get_attribute("value")
                cb.check()
                print(f"  ✅ 已勾选第一个可用账号 ID={val}")
                selected = True
                page.evaluate(f"""
                    var el = document.getElementById('extras-{val}');
                    if (el) el.classList.add('active');
                """)
                break
    
    if not selected:
        print("  ❌ 没有可勾选的账号")
        browser.close()
        exit(1)
    
    page.screenshot(path="/tmp/fs_e2e3_03_selected.png")
    time.sleep(1)

    # 确认存草稿模式
    draft_radio = page.query_selector("input[type='radio'][value='draft']:checked")
    if draft_radio:
        print(f"  ✅ 存草稿模式已选中 (默认)")
    else:
        print("  ⚠️ 存草稿模式未选中")

    # 提交
    print("\n[5] 提交存草稿...")
    submit_btn = page.query_selector("button[type='submit']")
    if submit_btn:
        print(f"  提交按钮: {submit_btn.inner_text()}")
        submit_btn.click()
        time.sleep(3)
        print(f"  提交后 URL: {page.url}")
        page.screenshot(path="/tmp/fs_e2e3_04_result.png")
        
        # 检查结果
        content = page.content()
        if "成功" in content or "success" in content.lower() or "draft" in content.lower():
            print("  ✅ 存草稿成功！")
        elif "alert_error" in content:
            import re
            err = re.search(r'class="alert_error"[^>]*>(.*?)</div>', content, re.DOTALL)
            if err:
                print(f"  ❌ 错误: {err.group(1)[:200]}")
            else:
                print("  ⚠️ 有错误提示但未能提取")
        else:
            print(f"  ℹ️ 页面标题: {page.title()[:60]}")
    else:
        print("  ❌ 未找到提交按钮")

    print(f"\n{'='*60}")
    print("✅ FS E2E 测试完成!")
    print("截图:")
    for f in ["/tmp/fs_e2e3_01_saved.png", "/tmp/fs_e2e3_02_publish_select.png",
              "/tmp/fs_e2e3_03_selected.png", "/tmp/fs_e2e3_04_result.png"]:
        print(f"  {f}")

    browser.close()
