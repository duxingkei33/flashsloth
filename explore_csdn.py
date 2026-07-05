"""CSDN 创作中心探索 — 编辑器/发布规则/分类"""
import re, json, time, os, sqlite3, base64
from playwright.sync_api import sync_playwright

FS_URL = "http://localhost:5000"

def explore_csdn():
    # Get CSDN cookie from FS database
    conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
    row = conn.execute(
        "SELECT config_json FROM platform_accounts WHERE platform='csdn' AND user_id=1 AND is_active=1"
    ).fetchone()
    conn.close()
    
    if not row:
        print("❌ CSDN 账户未找到")
        return
    
    cj = json.loads(row[0])
    cookie_str = cj.get("cookie", "")
    
    if not cookie_str or len(cookie_str) < 100:
        print(f"❌ Cookie 无效 (长度={len(cookie_str)})")
        return
    
    print(f"✅ CSDN Cookie 有效，长度: {len(cookie_str)}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        
        # Set cookies
        for pair in cookie_str.split(';'):
            pair = pair.strip()
            if '=' in pair:
                name, value = pair.split('=', 1)
                context.add_cookies([{
                    'name': name.strip(),
                    'value': value.strip(),
                    'domain': '.csdn.net',
                    'path': '/',
                }])
        
        page = context.new_page()
        
        # ═══════════════════════════════════════
        # 1. 验证登录
        # ═══════════════════════════════════════
        print("\n=== 1. 验证 CSDN 登录 ===")
        page.goto("https://www.csdn.net/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        page.screenshot(path="/tmp/csdn_explore_01_home.png")
        
        body = page.content()
        if '退出' in body or 'duxingkei' in body.lower() or 'my.csdn.net' in body:
            print("✅ CSDN 已登录")
        else:
            print("⚠️ 登录状态待确认")
            # Try to check user info
            user_area = page.locator("[class*='user'], [class*='avatar'], [class*='login']").first
            if user_area.is_visible():
                print(f"  User area: {user_area.inner_text()[:100]}")
        
        # ═══════════════════════════════════════
        # 2. 进入创作中心
        # ═══════════════════════════════════════
        print("\n=== 2. 进入创作中心 ===")
        
        # Try different URLs for CSDN editor
        editor_urls = [
            "https://editor.csdn.net/md/",
            "https://mp.csdn.net/mp_blog/creation/editor",
            "https://blog.csdn.net/nav/write",
            "https://www.csdn.net/creation",
        ]
        
        editor_page = None
        editor_html = None
        
        for url in editor_urls:
            print(f"  尝试: {url}")
            try:
                page.goto(url)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(3000)
                body = page.content()
                
                # Check if we reached an editor page
                if 'editor' in url or 'write' in url or 'creation' in url:
                    if 'login' not in page.url.lower() and 'passport' not in page.url.lower():
                        editor_page = url
                        editor_html = body
                        print(f"  ✅ 跳转成功: {page.url}")
                        break
                    elif 'login' in page.url.lower() or 'passport' in page.url.lower():
                        print(f"  ⚠️ 被重定向到登录页: {page.url}")
                else:
                    print(f"  URL: {page.url}")
                    
                    # Check if we see an editor
                    editor_elements = page.locator("#editor, .editor, [class*='editor'], textarea, [contenteditable]")
                    if editor_elements.count() > 0:
                        print(f"  ✅ 找到编辑器元素 ({editor_elements.count()}个)")
                        editor_page = url
                        editor_html = body
                        break
            except Exception as e:
                print(f"  ❌ 错误: {str(e)[:80]}")
        
        if not editor_page:
            print("\n⚠️ 未直接进入编辑器，尝试点击'写文章'")
            # Try to find and click "写文章" button
            write_btns = page.locator("text=写文章, text=写博客, text=创作, [class*='write'], [class*='publish']")
            if write_btns.count() > 0:
                for i in range(min(write_btns.count(), 5)):
                    btn = write_btns.nth(i)
                    if btn.is_visible():
                        print(f"  找到按钮: {btn.inner_text()[:30]}")
                        btn.click()
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(3000)
                        editor_html = page.content()
                        editor_page = page.url
                        print(f"  ✅ 点击后URL: {editor_page}")
                        break
        
        page.screenshot(path="/tmp/csdn_explore_02_editor.png")
        
        if editor_html:
            # ═══════════════════════════════════════
            # 3. 分析编辑器结构
            # ═══════════════════════════════════════
            print("\n=== 3. 分析编辑器结构 ===")
            
            # Find input fields
            inputs = re.findall(r'<input[^>]*>', editor_html)
            print(f"\n  输入框数量: {len(inputs)}")
            for inp in inputs[:15]:
                name = re.search(r'name=\"([^\"]+)\"', inp)
                placeholder = re.search(r'placeholder=\"([^\"]+)\"', inp)
                input_type = re.search(r'type=\"([^\"]+)\"', inp)
                n = name.group(1) if name else ''
                p = placeholder.group(1) if placeholder else ''
                t = input_type.group(1) if input_type else 'text'
                if n or p:
                    print(f"    <input type={t} name={n} placeholder={p}>")
            
            # Find textareas
            textareas = re.findall(r'<textarea[^>]*>.*?</textarea>', editor_html, re.DOTALL)
            print(f"\n  Textarea 数量: {len(textareas)}")
            for ta in textareas[:5]:
                name = re.search(r'name=\"([^\"]+)\"', ta)
                placeholder = re.search(r'placeholder=\"([^\"]+)\"', ta)
                n = name.group(1) if name else ''
                p = placeholder.group(1) if placeholder else ''
                print(f"    <textarea name={n} placeholder={p}>")
            
            # Find select/dropdown
            selects = re.findall(r'<select[^>]*>.*?</select>', editor_html, re.DOTALL)
            print(f"\n  下拉选择框数量: {len(selects)}")
            for sel in selects[:5]:
                name = re.search(r'name=\"([^\"]+)\"', sel)
                options = re.findall(r'<option[^>]*value=\"([^\"]*)\"[^>]*>([^<]+)</option>', sel)
                n = name.group(1) if name else ''
                print(f"    <select name={n}> ({len(options)} options)")
                for val, text in options[:5]:
                    print(f"      <option value={val}> {text}")
            
            # Find contenteditable divs (rich text editor)
            contenteditables = re.findall(r'<div[^>]*contenteditable[^>]*>', editor_html)
            print(f"\n  富文本编辑区: {len(contenteditables)}")
            
            # Find upload/button elements
            upload_btns = re.findall(r'upload|插入图片|上传|附件|image', editor_html, re.IGNORECASE)
            print(f"\n  上传相关关键词: {len(set(upload_btns))}")
            
            # Find category/tag elements
            categories = re.findall(r'分类|类别|栏目|专栏|tag|标签|type', editor_html, re.IGNORECASE)
            print(f"\n  分类/标签关键词: {len(set(categories))}")
            
            # ═══════════════════════════════════════
            # 4. 获取页面上的可见文本（编辑器UI）
            # ═══════════════════════════════════════
            print("\n=== 4. 编辑器可见UI ===")
            visible_text = page.locator("body").inner_text()
            lines = [l.strip() for l in visible_text.split('\n') if l.strip() and len(l.strip()) > 2]
            for l in lines[:40]:
                print(f"  {l}")
            
            # ═══════════════════════════════════════
            # 5. 检查API调用
            # ═══════════════════════════════════════
            print("\n=== 5. 网络请求分析 ===")
            
            # Monitor API requests
            api_requests = []
            def capture_request(request):
                url = request.url
                if 'api' in url.lower() or 'upload' in url.lower() or 'article' in url.lower():
                    api_requests.append({
                        'url': url,
                        'method': request.method,
                        'headers': dict(request.headers),
                    })
            
            page.on("request", capture_request)
            
            # Reload editor to capture API calls
            if editor_page:
                print(f"  重新加载编辑器以捕获API: {editor_page}")
                page.goto(editor_page)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(5000)
            
            # Analyze captured requests
            print(f"\n  捕获到 {len(api_requests)} 个API请求:")
            for req in api_requests[:20]:
                print(f"    {req['method']} {req['url'][:100]}")
            
            page.screenshot(path="/tmp/csdn_explore_03_full.png")
        
        # ═══════════════════════════════════════
        # 6. 探索个人创作页
        # ═══════════════════════════════════════
        print("\n=== 6. 探索个人创作管理页 ===")
        
        manage_urls = [
            "https://mp.csdn.net/mp_blog/manage/article",
            "https://blog.csdn.net/duxingkei?type=blog",
            "https://www.csdn.net/my",
        ]
        
        for url in manage_urls:
            try:
                page.goto(url)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(3000)
                if 'login' not in page.url.lower() and 'passport' not in page.url.lower():
                    print(f"  ✅ 管理页: {page.url}")
                    page.screenshot(path=f"/tmp/csdn_explore_04_manage.png")
                    
                    # Look for article list
                    articles = page.locator("[class*='article'], [class*='blog'], [class*='item'], [class*='list']").first
                    if articles.is_visible():
                        print(f"  文章列表可见: {articles.inner_text()[:200]}")
                    break
                else:
                    print(f"  ⚠️ 被重定向: {page.url}")
            except Exception as e:
                print(f"  ❌ {url}: {str(e)[:60]}")
        
        browser.close()
        print("\n✅✅✅ CSDN 探索完成")

if __name__ == "__main__":
    explore_csdn()
