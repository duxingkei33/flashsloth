"""E2E 测试：amobbs 存草稿 + 图片 + 附件"""
import re, json, time, os, sqlite3
from playwright.sync_api import sync_playwright

FS_URL = "http://localhost:5000"
ADMIN_USER = "admin_redacted"
ADMIN_PASS = "aA123456"

def setup_test_files():
    out_dir = "/tmp/e2e_amobbs_files"
    os.makedirs(out_dir, exist_ok=True)
    try:
        from PIL import Image, ImageDraw
        img = Image.new('RGB', (200, 100), color=(200, 100, 50))
        d = ImageDraw.Draw(img)
        d.text((20, 35), "Amobbs Test", fill=(255, 255, 255))
        img.save(os.path.join(out_dir, "amobbs_test.png"))
    except:
        with open(os.path.join(out_dir, "amobbs_test.png"), "wb") as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
    import zipfile
    with zipfile.ZipFile(os.path.join(out_dir, "code.zip"), 'w') as zf:
        zf.writestr("main.py", 'print("Amobbs E2E Test")\n')
    return out_dir

def e2e_test():
    files_dir = setup_test_files()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        # Login FS
        print("=== 1. 登录 FS ===")
        page.goto(f"{FS_URL}/login")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='username']", ADMIN_USER)
        page.fill("input[name='password']", ADMIN_PASS)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        print("✅ 登录成功")

        # Create article
        print("\n=== 2. 创建文章 ===")
        ts = int(time.time())
        test_title = f"E2E-Amobbs-{ts}"
        test_body = f"""## Amobbs测试 {ts}

这是一段**测试正文**，含*斜体*和`代码引用`。

### 图片
![amobbs测试](/static/uploads/amobbs_test.png)

### 代码
```python
print("Hello Amobbs!")
```

### 附件
[附件下载](/static/uploads/code.zip)

> 测试引用
"""
        page.goto(f"{FS_URL}/post/new")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='title']", test_title)
        page.fill("textarea[name='body']", test_body)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")

        # Get article ID
        conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
        row = conn.execute("SELECT id FROM articles WHERE title=? ORDER BY id DESC LIMIT 1", (test_title,)).fetchone()
        art_id = row[0] if row else None
        conn.close()
        assert art_id, "❌ 文章创建失败"
        print(f"✅ 文章ID={art_id}")

        # Upload test files
        print("\n=== 3. 上传测试文件 ===")
        fs_upload = "/home/duxingkei/.hermes/flashsloth/static/uploads"
        os.makedirs(fs_upload, exist_ok=True)
        import shutil
        for f in ["amobbs_test.png", "code.zip"]:
            src = os.path.join(files_dir, f)
            dst = os.path.join(fs_upload, f)
            shutil.copy(src, dst)
            print(f"  ✅ {f} ({os.path.getsize(dst)} bytes)")

        # Compile preview check
        print("\n=== 4. 编译预览 ===")
        page.goto(f"{FS_URL}/compile/{art_id}")
        page.wait_for_load_state("networkidle")
        html = page.content()
        if '&lt;p&gt;' in html or '<p>' in html:
            # Check if it's in the preview pane (safe filter) or code pane
            if '&lt;p&gt;' in html:
                print("⚠️ 代码窗格仍有 <p> 标签编码")
            else:
                print("  预览面板有HTML <p> 标签（正常）")
        else:
            print("✅ 无 <p> 标签问题")
        
        # Check BBCode 
        for tag in ['[b]', '[size=', '[img]', '[code]', '[url=', '[quote]']:
            if tag in html:
                print(f"  ✅ {tag}")

        # Publish select
        print("\n=== 5. 发布选择页 ===")
        page.goto(f"{FS_URL}/publish/select/{art_id}")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/fs_e2e_amobbs_01.png")
        
        # 勾选amobbs账号 (ID=1)
        amobbs_cb = page.locator("input[type='checkbox'][value='1']").first
        if amobbs_cb.count() > 0:
            amobbs_cb.check()
            print("✅ 已勾选 amobbs 账号(ID=1)")
            page.wait_for_timeout(2000)
        else:
            print("⚠️ 未找到amobbs账号")
        
        # 检查存草稿是否可用
        draft_radio = page.locator("input[type='radio'][value='draft']").first
        if draft_radio.count() > 0:
            disabled = draft_radio.is_disabled()
            print(f"  存草稿 radio: disabled={disabled}")
            if not disabled:
                draft_radio.check()
                print("✅ 存草稿可用")
            else:
                print("⚠️ 存草稿被禁用")
        
        # 选择板块
        forum_select = page.locator("select[name='forum_fid_1']").first
        if forum_select.count() > 0:
            page.wait_for_timeout(3000)
            opt = forum_select.locator("option:not([value=''])").first
            if opt.count() > 0:
                val = opt.get_attribute("value")
                if val:
                    forum_select.select_option(val)
                    print(f"✅ 已选择板块 fid={val}")
        
        page.screenshot(path="/tmp/fs_e2e_amobbs_02_ready.png")

        # Submit
        print("\n=== 6. 提交 ===")
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/fs_e2e_amobbs_03_result.png")
        
        flash_el = page.locator(".alert-success, .flash-success").first
        if flash_el.count() > 0:
            print(f"  Flash: {flash_el.inner_text()[:100]}")
        
        # Check DB
        print("\n=== 7. 数据库记录 ===")
        conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT pl.*, pa.account_name, pa.platform FROM publish_log pl "
            "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
            "WHERE pl.article_id=? ORDER BY pl.id DESC LIMIT 3",
            (art_id,)
        ).fetchall()
        for r in rows:
            d = dict(r)
            print(f"  id={d['id']} platform={d.get('platform','')} status={d['status']} message={d.get('message','')}")
            print(f"  url={d.get('url','')}")
        conn.close()

        # Verify on amobbs.com
        print("\n=== 8. 验证 amobbs.com ===")
        conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
        row = conn.execute('SELECT config_json FROM platform_accounts WHERE id=1').fetchone()
        cj = json.loads(row[0])
        conn.close()
        
        cookie_str = cj['cookie']
        amobbs_ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        for pair in cookie_str.split(';'):
            pair = pair.strip()
            if '=' in pair:
                name, value = pair.split('=', 1)
                amobbs_ctx.add_cookies([{
                    'name': name.strip(),
                    'value': value.strip(),
                    'domain': '.amobbs.com',
                    'path': '/',
                }])
        
        am_page = amobbs_ctx.new_page()
        am_page.goto("https://www.amobbs.com/")
        am_page.wait_for_load_state("networkidle")
        logged_in = 'duxingkei' in am_page.content()
        print(f"  amobbs 登录: {'✅' if logged_in else '❌'}")
        
        if logged_in:
            # Check draft recovery on newthread page
            am_page.goto("https://www.amobbs.com/forum.php?mod=post&action=newthread&fid=2")
            am_page.wait_for_load_state("networkidle")
            am_html = am_page.content()
            if '恢复数据' in am_html or '草稿' in am_html:
                print("✅ amobbs 有草稿恢复功能")
            else:
                print("  amobbs 新帖页面：无草稿恢复提示")
            am_page.screenshot(path="/tmp/fs_e2e_amobbs_04_forum.png")
        
        amobbs_ctx.close()

        # Cleanup
        print("\n=== 9. 清理 ===")
        import shutil
        shutil.rmtree(files_dir, ignore_errors=True)
        for f in ["amobbs_test.png", "code.zip"]:
            fp = os.path.join(fs_upload, f)
            if os.path.exists(fp):
                os.remove(fp)
        
        browser.close()
        print("✅✅✅ Amobbs E2E测试完成")

if __name__ == "__main__":
    e2e_test()
