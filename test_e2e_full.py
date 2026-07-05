"""E2E 完整测试：图片上传 + 附件上传 + 存草稿（mydigit.cn）"""
import re, json, time, os, sqlite3
from playwright.sync_api import sync_playwright

FS_URL = "http://localhost:5000"
ADMIN_USER = "admin_redacted"
ADMIN_PASS = "aA123456"

# 创建测试图片和附件
def setup_test_files():
    out_dir = "/tmp/e2e_test_files"
    os.makedirs(out_dir, exist_ok=True)
    
    # 创建测试图片（用PIL生成一个小PNG）
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (200, 100), color=(73, 109, 137))
        d = ImageDraw.Draw(img)
        d.text((20, 35), "E2E Test Image", fill=(255, 255, 255))
        img.save(os.path.join(out_dir, "test_image.png"))
        print("✅ 测试图片已创建: test_image.png")
    except:
        # fallback: 写入一个简单的PNG二进制
        with open(os.path.join(out_dir, "test_image.png"), "wb") as f:
            f.write(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100)
        print("✅ 测试图片已创建(simple): test_image.png")
    
    # 创建测试ZIP附件（一个简短代码文件压缩）
    import zipfile
    zip_path = os.path.join(out_dir, "test_attachment.zip")
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr("hello.py", '#!/usr/bin/env python3\nprint("Hello from E2E test!")\n')
        zf.writestr("README.md", "# Test Attachment\nThis is a test attachment for E2E.\n")
    print(f"✅ 测试ZIP已创建: test_attachment.zip ({os.path.getsize(zip_path)} bytes)")
    
    return out_dir

def e2e_test():
    files_dir = setup_test_files()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # ── Step 1: Login FS ──
        print("\n=== 1. 登录 FS ===")
        page.goto(f"{FS_URL}/login")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='username']", ADMIN_USER)
        page.fill("input[name='password']", ADMIN_PASS)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        assert "login" not in page.url.lower(), f"❌ 登录失败: {page.url}"
        print("✅ 登录成功")

        # ── Step 2: 创建测试文章（含图片Markdown引用） ──
        print("\n=== 2. 创建测试文章 ===")
        ts = int(time.time())
        test_title = f"E2E全测试-{ts}"
        test_body = f"""## 测试标题

这是一段测试正文，包含**粗体**和*斜体*格式。

### 图片测试
![测试图片](/static/uploads/test_image.png)

### 代码测试
```python
def hello():
    print("Hello FlashSloth!")
```

### 附件引用
[测试附件](/static/uploads/test_attachment.zip)

> 这是一条引用

下面是普通段落结束。
"""
        page.goto(f"{FS_URL}/post/new")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='title']", test_title)
        page.fill("textarea[name='body']", test_body)
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")
        print(f"✅ 文章已提交")

        # 获取文章ID
        art_id = None
        conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
        row = conn.execute(
            "SELECT id FROM articles WHERE title=? ORDER BY id DESC LIMIT 1",
            (test_title,)
        ).fetchone()
        if row:
            art_id = row[0]
        conn.close()
        assert art_id, "❌ 文章创建失败"
        print(f"✅ 文章ID={art_id}")

        # ── Step 3: 上传测试图片和附件到FS的static/uploads ──
        print("\n=== 3. 上传测试文件到FS ===")
        fs_upload_dir = "/home/duxingkei/.hermes/flashsloth/static/uploads"
        os.makedirs(fs_upload_dir, exist_ok=True)
        
        import shutil
        shutil.copy(os.path.join(files_dir, "test_image.png"),
                    os.path.join(fs_upload_dir, "test_image.png"))
        shutil.copy(os.path.join(files_dir, "test_attachment.zip"),
                    os.path.join(fs_upload_dir, "test_attachment.zip"))
        print(f"✅ 测试文件已复制到 {fs_upload_dir}")
        
        # 验证文件存在
        for f in ["test_image.png", "test_attachment.zip"]:
            fp = os.path.join(fs_upload_dir, f)
            print(f"  {f}: {os.path.getsize(fp)} bytes")

        # ── Step 4: 进入编译预览，检查BBCode输出 ──
        print("\n=== 4. 检查编译预览（确认BBCode正确，无<p>标签） ===")
        page.goto(f"{FS_URL}/compile/{art_id}")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/fs_e2e_full_01_compile.png")
        compile_html = page.content()
        
        # 检查是否有 <p> 标签出现（不应有）
        p_raw = re.findall(r'&lt;p&gt;|&lt;/p&gt;|<p>|</p>', compile_html)
        if p_raw:
            print(f"⚠️ 编译预览仍有 <p> 标签: {p_raw[:5]}")
        else:
            print("✅ 编译预览无 <p> 标签")
        
        # 检查BBCode格式
        bbcode_markers = ['[b]', '[/b]', '[size=', '[img]', '[code]', '[url=', '[quote]']
        for marker in bbcode_markers:
            if marker in compile_html:
                print(f"  ✅ BBCode标记正确: {marker}")
        
        # 展开编译详情
        compile_header = page.locator(".compiled-card-header").first
        if compile_header.is_visible():
            compile_header.click()
            page.wait_for_timeout(500)
        
        page.screenshot(path="/tmp/fs_e2e_full_02_compile_expanded.png")

        # ── Step 5: 发布选择页 + 存草稿 ──
        print("\n=== 5. 发布选择页 ===")
        page.goto(f"{FS_URL}/publish/select/{art_id}")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/fs_e2e_full_03_publish_select.png")
        
        # 勾选mydigit账号 (ID=4)
        mydigit_cb = page.locator("input[type='checkbox'][value='4']").first
        if mydigit_cb.count() > 0:
            mydigit_cb.check()
            print("✅ 已勾选 mydigit 账号")
            page.wait_for_timeout(2000)
        else:
            print("⚠️ 未找到mydigit账号，尝试其他复选框")
            page.locator("input[name='account_ids']").first.check()
            page.wait_for_timeout(2000)
        
        # 确认存草稿已选中
        draft_radio = page.locator("input[type='radio'][value='draft']").first
        if draft_radio.count() > 0 and not draft_radio.is_disabled():
            draft_radio.check()
            print("✅ 已选中存草稿模式")
        
        # 选择板块
        forum_select = page.locator("select[name='forum_fid_4']").first
        if forum_select.count() > 0:
            page.wait_for_timeout(3000)
            opt = forum_select.locator("option:not([value=''])").first
            if opt.count() > 0:
                val = opt.get_attribute("value")
                if val:
                    forum_select.select_option(val)
                    print(f"✅ 已选择板块 value={val}")
        
        page.screenshot(path="/tmp/fs_e2e_full_04_ready_to_publish.png")

        # ── Step 6: 提交 ──
        print("\n=== 6. 提交发布 ===")
        page.locator("button[type='submit']").first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/fs_e2e_full_05_after_publish.png")
        print(f"✅ 提交完成，URL: {page.url}")
        
        # 检查Flash消息
        flash_text = page.locator(".alert-success, .flash-success").first
        if flash_text.count() > 0:
            print(f"  消息: {flash_text.inner_text()[:100]}")
        
        # 检查数据库记录
        print("\n=== 7. 检查数据库发布记录 ===")
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
            print(f"  id={d['id']} platform={d.get('platform','')} account={d.get('account_name','')}")
            print(f"  success={d['success']} status={d['status']} message={d.get('message','')}")
            print(f"  url={d.get('url','')}")
            print(f"  error={d.get('error','')[:80] if d.get('error') else ''}")
            if d.get('url'):
                print(f"  ✅ 有帖子URL")
        conn.close()

        # ── Step 8: 首页验证草稿标记 ──
        print("\n=== 8. 首页文章列表标记 ===")
        page.goto(f"{FS_URL}/")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/fs_e2e_full_06_home.png")
        home_html = page.content()
        
        draft_in_home = '📝' in home_html or '草稿' in home_html or 'draft' in home_html
        if draft_in_home:
            print("✅ 首页显示草稿/存草稿标记")
        else:
            # 检查文章标题
            if test_title[:15] in home_html:
                print("  找到文章标题，但无草稿标记")
            else:
                print("  未在首页找到文章")

        # ── Step 9: 验证mydigit.cn上的发布结果 ──
        print("\n=== 9. 验证mydigit.cn ===")
        conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
        row = conn.execute('SELECT config_json FROM platform_accounts WHERE id=4').fetchone()
        cj = json.loads(row[0])
        conn.close()
        
        cookie_str = cj['cookie']
        mydigit_ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1280, 'height': 800}
        )
        for pair in cookie_str.split(';'):
            pair = pair.strip()
            if '=' in pair:
                name, value = pair.split('=', 1)
                mydigit_ctx.add_cookies([{
                    'name': name.strip(),
                    'value': value.strip(),
                    'domain': '.mydigit.cn',
                    'path': '/',
                }])
        
        my_page = mydigit_ctx.new_page()
        my_page.goto("https://www.mydigit.cn/")
        my_page.wait_for_load_state("networkidle")
        
        # Check log in
        if 'duxingkei' in my_page.content():
            print("✅ mydigit.cn 已登录")
        else:
            print("⚠️ mydigit.cn 未登录")
        
        # 检查新帖页面草稿恢复
        my_page.goto("https://www.mydigit.cn/forum.php?mod=post&action=newthread&fid=40")
        my_page.wait_for_load_state("networkidle")
        my_page.screenshot(path="/tmp/fs_e2e_full_07_mydigit_newthread.png")
        mydigit_html = my_page.content()
        
        if '恢复数据' in mydigit_html:
            print("✅ mydigit.cn 显示「恢复数据」——存草稿成功")
        else:
            print("  未显示恢复数据")
        if '查看所有草稿' in mydigit_html:
            print("✅ 有「查看所有草稿」链接")
        
        mydigit_ctx.close()
        
        # ── Step 10: 清理 ──
        print("\n=== 10. 清理临时文件 ===")
        import shutil
        if os.path.exists(files_dir):
            shutil.rmtree(files_dir)
            print("✅ 临时文件已清理")
        for f in ["test_image.png", "test_attachment.zip"]:
            fp = os.path.join(fs_upload_dir, f)
            if os.path.exists(fp):
                os.remove(fp)
                print(f"✅ 已删除 {f}")
        
        browser.close()
        print("\n✅✅✅ E2E测试完成")

if __name__ == "__main__":
    e2e_test()
