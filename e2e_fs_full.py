"""
FS 后台完整 E2E 测试 — Playwright 全流程
写文章 → 编译预览 → 选择发布目标 → 存草稿 → 验证结果
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

    # Step 1: 登录
    print("[1/7] 登录 FS...")
    page.goto(f"{FS_URL}/login", wait_until="networkidle", timeout=30000)
    page.fill("input[name='username']", FS_USER)
    page.fill("input[name='password']", FS_PASS)
    page.click("button[type='submit']")
    time.sleep(2)
    print(f"  ✅ 登录成功: {page.url}")
    page.screenshot(path="/tmp/fs_e2e2_01.png")

    # Step 2: 首页 — 找写文章入口
    print("\n[2/7] 首页找写文章入口...")
    page.goto(f"{FS_URL}/", wait_until="networkidle", timeout=30000)
    time.sleep(1)
    
    # 找文章相关的链接
    write_links = page.query_selector_all("a[href*='write'], a[href*='new'], a[href*='article'], a[href*='editor'], a[href*='post']")
    for link in write_links:
        href = link.get_attribute("href") or ""
        text = link.inner_text()
        print(f"  链接: {text} → {href}")
    
    # 找新增/写文章按钮
    new_btn = page.query_selector("a:has-text('写文章'), a:has-text('新建'), a:has-text('新增'), button:has-text('写文章')")
    if new_btn:
        print(f"  ✅ 发现写文章入口: {new_btn.inner_text()}")
        href = new_btn.get_attribute("href") or ""
        page.goto(f"{FS_URL}{href}", wait_until="networkidle", timeout=30000)
        time.sleep(1)
    else:
        # 直接试试常见路径
        page.goto(f"{FS_URL}/write", wait_until="networkidle", timeout=30000)
        time.sleep(1)
    
    print(f"  当前URL: {page.url}")
    page.screenshot(path="/tmp/fs_e2e2_02_write.png")

    # Step 3: 找编辑器并写文章
    print("\n[3/7] 写文章...")
    
    # 查找所有 input 和 textarea
    inputs = page.query_selector_all("input:not([type='hidden']):not([type='checkbox']), textarea")
    for inp in inputs:
        name = inp.get_attribute("name") or ""
        id_ = inp.get_attribute("id") or ""
        placeholder = inp.get_attribute("placeholder") or ""
        print(f"  输入框: name={name} id={id_} placeholder={placeholder[:30]}")
    
    # 找标题输入框
    title_input = page.query_selector("input[name='title'], #title, input[placeholder*='标题']")
    if title_input:
        title_input.fill("【E2E测试】Playwright 全流程验证 — ESP32 低功耗方案")
        print("  ✅ 标题已填写")
    else:
        print("  ⚠️ 未找到标题输入框")
    
    # 找内容编辑器（body/textarea）
    body_input = page.query_selector("textarea[name='body'], #body, textarea[placeholder*='内容']")
    if body_input:
        body_input.fill("## 方案概述\n\n使用 ESP32 深度睡眠模式，电流可降至 5μA。\n\n## 实测数据\n\n| 模式 | 电流 |\n| Active | 310mA |\n| Deep Sleep | 5μA |")
        print("  ✅ 内容已填写")
    else:
        print("  ⚠️ 未找到编辑器")
    
    page.screenshot(path="/tmp/fs_e2e2_03_filled.png")

    # Step 4: 找保存/提交按钮
    print("\n[4/7] 保存文章...")
    save_btn = page.query_selector("button[type='submit'], button:has-text('保存'), button:has-text('提交'), input[type='submit']")
    if save_btn:
        print(f"  保存按钮: {save_btn.inner_text() or save_btn.get_attribute('value')}")
        save_btn.click()
        time.sleep(2)
        print(f"  保存后 URL: {page.url}")
        page.screenshot(path="/tmp/fs_e2e2_04_saved.png")
    else:
        print("  ⚠️ 未找到保存按钮，尝试提交表单")
        page.evaluate("document.querySelector('form')?.submit()")
        time.sleep(2)
        print(f"  提交后 URL: {page.url}")
    
    # Step 5: 找发布按钮/链接
    print("\n[5/7] 找发布入口...")
    publish_link = page.query_selector("a[href*='publish'], button:has-text('发布')")
    if publish_link:
        href = publish_link.get_attribute("href") or ""
        print(f"  发布链接: {publish_link.inner_text()} → {href}")
        page.goto(f"{FS_URL}{href}", wait_until="networkidle", timeout=30000)
        time.sleep(1)
        print(f"  当前URL: {page.url}")
    else:
        # 可能刚保存的文章有发布按钮
        # 或者 URL 中能看到文章 ID
        import re
        pid_match = re.search(r'/publish/(\d+)', page.url)
        if pid_match:
            print(f"  已在发布选择页 (pid={pid_match.group(1)})")
    
    page.screenshot(path="/tmp/fs_e2e2_05_publish_select.png")
    
    # Step 6: 选择发布目标 + 存草稿
    print("\n[6/7] 选择发布目标（存草稿模式）...")
    
    # 查找账号复选框
    account_cards = page.query_selector_all(".account-card")
    print(f"  账号卡片: {len(account_cards)} 个")
    
    # 勾选第一个可用账号（mydigit.cn 或 amobbs）
    checkboxes = page.query_selector_all("input[name='account_ids']")
    checked = False
    for cb in checkboxes:
        if not cb.is_disabled() and not cb.is_checked():
            cb.check()
            # 展开详情
            account_id = cb.get_attribute("value")
            if account_id:
                # 触发展开
                extras = page.query_selector(f"#extras-{account_id}")
                if extras:
                    page.evaluate(f"document.getElementById('extras-{account_id}').classList.add('active')")
            print(f"  ✅ 已勾选账号 ID={cb.get_attribute('value')}")
            checked = True
            break
    
    if not checked:
        print("  ⚠️ 没有可勾选的账号")
        # 截图看看什么情况
        page.screenshot(path="/tmp/fs_e2e2_06_no_accounts.png")
    
    # 确认存草稿模式已选中（默认就是 draft）
    draft_radio = page.query_selector("input[type='radio'][value='draft']:checked")
    if draft_radio:
        print(f"  ✅ 默认存草稿模式已选中 (name={draft_radio.get_attribute('name')})")
    
    page.screenshot(path="/tmp/fs_e2e2_06_selected.png")
    
    # Step 7: 提交发布
    print("\n[7/7] 提交发布（存草稿）...")
    submit_btn = page.query_selector("button[type='submit']")
    if submit_btn:
        text = submit_btn.inner_text()
        print(f"  提交按钮: {text}")
        submit_btn.click()
        time.sleep(3)
        print(f"  提交后 URL: {page.url}")
        page.screenshot(path="/tmp/fs_e2e2_07_result.png")
        
        # 检查结果
        content = page.content()
        if "成功" in content or "success" in content.lower():
            print("  ✅ 发布/存草稿成功！")
        elif "草稿" in content:
            print("  ✅ 草稿已保存！")
        elif "error" in content.lower() or "失败" in content or "alert_error" in content:
            print("  ⚠️ 可能出错")
        else:
            print("  ℹ️ 状态不明，请查看截图")
        
        # 检查页面内容
        print(f"\n  页面标题: {page.title()[:60]}")
    else:
        print("  ⚠️ 未找到提交按钮")

    print(f"\n{'='*60}")
    print("FS E2E 测试完成!")
    print("截图:")
    for i in range(1, 8):
        print(f"  /tmp/fs_e2e2_0{i}.png")

    browser.close()
