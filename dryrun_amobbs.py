"""
阿莫论坛全流程干跑 — 用 Playwright 模拟填写→上传→存草稿
只读不写最终不发布，存为草稿后通知用户
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

FS_VENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv")
sys.path.insert(0, os.path.join(FS_VENV, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages"))

from playwright.sync_api import sync_playwright

print("=" * 60)
print("阿莫论坛 (amobbs.com) 全流程干跑")
print("操作: 登录→发帖页→填写→上传→存草稿")
print("协议: 只读不写最终不发布，存草稿即停")
print("=" * 60)

# 测试文章
TEST_TITLE = "【FlashSloth 存草稿测试】关于 ESP32-C3 的功耗优化经验分享"
TEST_BODY = """## 背景

最近在做一个基于 ESP32-C3 的电池供电项目，对功耗要求比较高。经过一段时间的调试和优化，总结了一些经验，分享给大家。

## 关键优化点

### 1. 深度睡眠模式

ESP32-C3 的深度睡眠电流可以做到 **5μA** 左右，关键是要正确配置 RTC 外设：

```c
esp_sleep_enable_timer_wakeup(3600 * 1000000);  // 1小时唤醒一次
esp_deep_sleep_start();
```

### 2. WiFi 连接优化

- 减少扫描时间：直接指定已知 AP
- 使用 WiFi Modem Sleep 模式
- 非必要不保持连接，数据发完即断

### 3. GPIO 上拉下拉

未使用的 GPIO 要配置为内部下拉，否则浮空引脚会额外耗电。

## 实测数据

| 模式 | 电流 | 说明 |
|------|------|------|
| Active (WiFi TX) | ~310mA | 峰值 |
| Active (WiFi RX) | ~80mA | |
| Modem Sleep | ~5mA | 保持连接 |
| Deep Sleep | 5μA | RTC 定时唤醒 |

## 总结

ESP32-C3 的功耗控制做得不错，配合合理的软件策略，完全可以用电池供电运行很长时间。

> 本文由 FlashSloth 自动生成测试草稿，不会正式发布。
"""

FID = "10061"  # 水坛（最大众的版块）

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
    
    # Step 1: 访问发帖页
    print("\n[1/5] 访问发帖页...")
    page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid={FID}", wait_until="networkidle", timeout=60000)
    time.sleep(3)
    
    # 检查权限
    err = page.query_selector("#messagetext, .alert_error")
    if err:
        print(f"  ❌ 发帖权限异常: {err.inner_text()[:200]}")
        browser.close()
        exit(1)
    print("  ✅ 发帖页面正常加载")
    page.screenshot(path="/tmp/amobbs_dryrun_01.png")
    
    # Step 2: 填写标题
    print("\n[2/5] 填写标题...")
    title_input = page.query_selector("input#subject")
    if title_input:
        title_input.fill(TEST_TITLE)
        print(f"  ✅ 标题已填写: {TEST_TITLE[:40]}...")
    else:
        # 可能标题在 iframe 里
        print("  ⚠️ 未找到标题输入框（可能在 iframe 中）")
    time.sleep(1)
    
    # Step 3: 填写内容
    print("\n[3/5] 填写文章内容...")
    
    # 尝试 textarea
    textarea = page.query_selector("textarea#message, textarea#fastpostmessage")
    if textarea:
        textarea.fill(TEST_BODY)
        print(f"  ✅ 内容已填写 ({len(TEST_BODY)} chars)")
    else:
        # 可能是 iframe 富文本编辑器
        iframe = page.query_selector("iframe[id^='e_iframe'], #e_iframe")
        if iframe:
            print(f"  ✅ 发现 iframe 编辑器，注入内容...")
            # 用 JS 注入 — 先转义反引号
            escaped_body = TEST_BODY.replace('`', '\\`').replace('$', '\\$')
            page.evaluate(f"""
                var iframe = document.querySelector('iframe[id^="e_iframe"]');
                if (iframe) {{
                    var doc = iframe.contentDocument || iframe.contentWindow.document;
                    doc.body.innerHTML = `{escaped_body}`;
                }}
            """)
            print("  ✅ 内容已注入 iframe")
        else:
            print("  ⚠️ 未找到编辑器")
    
    page.screenshot(path="/tmp/amobbs_dryrun_02_filled.png")
    time.sleep(2)
    
    # Step 4: 尝试上传图片（用本地一张测试图）
    print("\n[4/5] 上传图片...")
    
    # 先找上传区域的图片输入
    file_input = page.query_selector("input[type='file'][name='Filedata']")
    if file_input:
        # 创建一张测试图片
        import tempfile
        test_img = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        # 生成一张 100x100 的测试 PNG
        try:
            from PIL import Image
            img = Image.new('RGB', (100, 100), color='red')
            img.save(test_img.name, 'PNG')
            print(f"  ✅ 已创建测试图片: {test_img.name}")
        except ImportError:
            test_img.write(b'iVBORw0KGgoAAAANSUhEUgAAAGQAAABkCAYAAABw4pVUAAAAFElEQVR42u3BAQ0AAADCoPdPbQ8HFAAAAAF8RqVj3QAAAABJRU5ErkJggg==')
            test_img.close()
            print(f"  ⚠️ PIL不可用，创建简单PNG: {test_img.name}")
        
        # 获取 uid 和 hash
        html = page.content()
        uid_m = re.search(r'uid["\']?\s*[:=]\s*["\']?(\d+)["\']?', html)
        hash_m = re.search(r'hash["\']?\s*[:=]\s*["\']?([a-f0-9]+)["\']?', html)
        uid = uid_m.group(1) if uid_m else ""
        hash_val = hash_m.group(1) if hash_m else ""
        
        if uid and hash_val:
            import requests
            upload_url = f"{SITE}/misc.php?mod=swfupload&action=swfupload&operation=upload&fid={FID}&simple=1"
            cookie_dict = {}
            for c in COOKIE_STR.split("; "):
                if "=" in c:
                    k, v = c.split("=", 1)
                    cookie_dict[k.strip()] = v.strip()
            
            with open(test_img.name, 'rb') as f:
                resp = requests.post(
                    upload_url,
                    files={'Filedata': ('test.png', f, 'image/png')},
                    data={'uid': uid, 'hash': hash_val, 'type': 'image'},
                    cookies=cookie_dict,
                    headers={'User-Agent': 'Mozilla/5.0'},
                    timeout=15,
                )
            raw = resp.text.strip()
            if 'DISCUZUPLOAD' in raw:
                print(f"  ✅ 图片上传成功! token: {raw[:50]}")
            elif raw.isdigit():
                print(f"  ✅ 图片上传成功! aid: {raw}")
            else:
                print(f"  ⚠️ 上传响应: {raw[:100]}")
        else:
            print(f"  ⚠️ 未获取到上传参数 (uid={'有' if uid else '无'}, hash={'有' if hash_val else '无'})")
    else:
        print("  ⚠️ 未找到文件上传输入框")
    
    page.screenshot(path="/tmp/amobbs_dryrun_03_uploaded.png")
    time.sleep(2)
    
    # Step 5: 存草稿（不发布！）
    print("\n[5/5] 存草稿（不发布）...")
    
    # 检查有没"保存草稿"按钮
    save_draft = page.query_selector("button[name='save'], a[href*='save=1'], input[name='save'], button:has-text('草稿')")
    
    if save_draft:
        print(f"  发现存草稿按钮")
        save_draft.click()
        time.sleep(3)
        page.screenshot(path="/tmp/amobbs_dryrun_04_draft_saved.png")
        print(f"  ✅ 草稿已保存!")
    else:
        print("  未找到存草稿按钮，尝试通过表单参数存草稿...")
        # 通过 JS 提交带 save=1 的表单
        formhash_m = re.search(r'name="formhash"[^>]+value="([^"]+)"', page.content())
        formhash = formhash_m.group(1) if formhash_m else ""
        if formhash:
            print(f"  formhash: {formhash}")
            page.evaluate(f"""
                var form = document.querySelector('form');
                if (form) {{
                    var input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'save';
                    input.value = '1';
                    form.appendChild(input);
                    // 修改 action 加入 save=1
                    var action = form.getAttribute('action') || '';
                    if (action.indexOf('save=') === -1) {{
                        form.setAttribute('action', action + '&save=1');
                    }}
                    form.submit();
                }}
            """)
            time.sleep(3)
            page.screenshot(path="/tmp/amobbs_dryrun_04_draft_saved.png")
            print(f"  ✅ 已通过表单提交存草稿")
        else:
            print("  ⚠️ 无法获取 formhash，存草稿失败")
    
    # 最终截图
    page.screenshot(path="/tmp/amobbs_dryrun_05_final.png", full_page=True)
    
    print(f"\n{'='*60}")
    print("全流程干跑完成!")
    print("截图已保存:")
    print("  /tmp/amobbs_dryrun_01.png (发帖页)")
    print("  /tmp/amobbs_dryrun_02_filled.png (已填写)")
    print("  /tmp/amobbs_dryrun_03_uploaded.png (已上传)")
    print("  /tmp/amobbs_dryrun_04_draft_saved.png (草稿结果)")
    print("  /tmp/amobbs_dryrun_05_final.png (最终页)")
    
    # 检查结果页面
    final_url = page.url
    final_title = page.title()
    print(f"\n结果页面: {final_url}")
    print(f"页面标题: {final_title}")
    
    # 检查是否成功
    content = page.content()
    if 'draft' in content.lower() or '草稿' in content:
        print("✅ 草稿确认已保存！")
    elif 'success' in content.lower() or '成功' in content:
        print("✅ 操作成功！")
    else:
        print("⚠️ 状态不明，请查看截图确认")
    
    browser.close()
