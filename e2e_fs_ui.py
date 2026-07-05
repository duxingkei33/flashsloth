"""
FS 后台 E2E 测试 — 用 Playwright 模拟用户操作
检查：登录→写文章→发布/存草稿 全流程
"""
import json, time, sys, os, re

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
        viewport={"width": 1920, "height": 1080},
        locale="zh-CN"
    )
    page = ctx.new_page()

    # Step 1: 登录
    print("[1/6] 登录 FS 后台...")
    page.goto(f"{FS_URL}/login", wait_until="networkidle", timeout=30000)
    page.fill("input[name='username']", FS_USER)
    page.fill("input[name='password']", FS_PASS)
    page.click("button[type='submit']")
    time.sleep(2)
    print(f"  登录后 URL: {page.url}")
    print(f"  标题: {page.title()[:60]}")
    page.screenshot(path="/tmp/fs_e2e_01_loggedin.png")

    # Step 2: 账号管理页
    print("\n[2/6] 查看账号管理...")
    page.goto(f"{FS_URL}/accounts", wait_until="networkidle", timeout=30000)
    time.sleep(1)
    print(f"  页面标题: {page.title()[:60]}")
    # 检查是否有 amobbs 和 mydigit 账号
    content = page.content()
    for name in ["amobbs", "mydigit", "oshwhub"]:
        if name in content.lower():
            print(f"  ✅ 发现 {name} 账号")
    page.screenshot(path="/tmp/fs_e2e_02_accounts.png")

    # Step 3: 写文章页（编辑器）
    print("\n[3/6] 打开编辑器写文章...")
    # 找编辑器页面
    page.goto(f"{FS_URL}/editor", wait_until="networkidle", timeout=30000)
    time.sleep(1)
    print(f"  编辑器页面: {page.url}")
    page.screenshot(path="/tmp/fs_e2e_03_editor.png")

    # 检查编辑器元素
    title_input = page.query_selector("input[name='title'], #title, input[placeholder*='标题']")
    body_area = page.query_selector("textarea, #body, .editor, [contenteditable]")
    if title_input:
        print(f"  ✅ 标题输入框: name={title_input.get_attribute('name')}")
        title_input.fill("【E2E测试】Playwright 全流程验证文章")
    else:
        print("  ⚠️ 未找到标题输入框")
    
    if body_area:
        tag = body_area.evaluate("el => el.tagName")
        print(f"  ✅ 编辑器: <{tag}>")
        body_area.fill("这是由 Playwright E2E 测试自动生成的文章，用于验证 FS 发布全流程。")
    else:
        print("  ⚠️ 未找到编辑器")

    page.screenshot(path="/tmp/fs_e2e_03_editor_filled.png")

    # Step 4: 编译预览
    print("\n[4/6] 查找编译预览功能...")
    compile_btn = page.query_selector("button:has-text('编译'), button:has-text('预览'), a:has-text('编译')")
    if compile_btn:
        print(f"  ✅ 发现编译/预览按钮: {compile_btn.inner_text()}")
        compile_btn.click()
        time.sleep(2)
        page.screenshot(path="/tmp/fs_e2e_04_compiled.png")
    else:
        print("  ⚠️ 未找到编译按钮")

    # Step 5: 发布页
    print("\n[5/6] 查看发布选择页...")
    # 尝试找发布相关按钮
    publish_btn = page.query_selector("button:has-text('发布'), a:has-text('发布'), button:has-text('发表')")
    if publish_btn:
        print(f"  ✅ 发现发布按钮: {publish_btn.inner_text()}")
        publish_btn.click()
        time.sleep(2)
        page.screenshot(path="/tmp/fs_e2e_05_publish.png")
        print(f"  发布页 URL: {page.url}")
    else:
        # 尝试直接访问发布选择页
        page.goto(f"{FS_URL}/publish", wait_until="networkidle", timeout=30000)
        time.sleep(1)
        print(f"  发布选择页 URL: {page.url}")
        page.screenshot(path="/tmp/fs_e2e_05_publish.png")

    # 检查发布页面是否有"存草稿"选项
    content = page.content()
    has_draft = "存草稿" in content or "draft" in content.lower() or "save" in content.lower()
    has_publish = "发布" in content or "发表" in content
    print(f"  存草稿选项: {'✅ 有' if has_draft else '❌ 无'}")
    print(f"  发布选项: {'✅ 有' if has_publish else '❌ 无'}")

    # Step 6: 检查发布选择页的详细选项
    print("\n[6/6] 发布选择页详细检查...")
    # 找平台选择
    checkboxes = page.query_selector_all("input[type='checkbox']")
    radios = page.query_selector_all("input[type='radio']")
    selects = page.query_selector_all("select")
    print(f"  复选框: {len(checkboxes)}, 单选: {len(radios)}, 下拉框: {len(selects)}")
    
    # 找发布模式选择（直接发布/存草稿）
    mode_options = page.query_selector_all("[name*='mode'], [name*='draft'], [name*='save'], [id*='mode'], [id*='draft']")
    if mode_options:
        for opt in mode_options:
            print(f"  发布模式选项: name={opt.get_attribute('name')} id={opt.get_attribute('id')}")
    else:
        print("  未找到发布模式选项（无存草稿切换）")
    
    # 找各平台的发布按钮/选项
    platform_sections = page.query_selector_all(".platform-item, .platform-card, [class*='platform']")
    print(f"  平台数量: {len(platform_sections)}")
    for ps in platform_sections[:5]:
        text = ps.inner_text()[:60]
        print(f"    {text}")

    page.screenshot(path="/tmp/fs_e2e_06_details.png", full_page=True)
    
    print(f"\n{'='*60}")
    print("FS E2E 检查完成!")
    print(f"截图已保存至 /tmp/fs_e2e_*.png")

    browser.close()
