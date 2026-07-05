"""CSDN 深度探索 — 分类/发布/上传API"""
import re, json, time, os, sqlite3
from playwright.sync_api import sync_playwright

def explore_csdn_deep():
    conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
    row = conn.execute(
        "SELECT config_json FROM platform_accounts WHERE platform='csdn' AND user_id=1 AND is_active=1"
    ).fetchone()
    conn.close()
    cj = json.loads(row[0])
    cookie_str = cj.get("cookie", "")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        for pair in cookie_str.split(';'):
            pair = pair.strip()
            if '=' in pair:
                name, value = pair.split('=', 1)
                context.add_cookies([{
                    'name': name.strip(), 'value': value.strip(),
                    'domain': '.csdn.net', 'path': '/',
                }])
        
        page = context.new_page()
        
        # Track all API responses
        api_responses = []
        
        def capture_response(response):
            url = response.url
            if 'bizapi.csdn.net' in url or 'passport.csdn.net' in url:
                try:
                    body = response.text()
                    api_responses.append({
                        'url': url,
                        'method': response.request.method,
                        'status': response.status,
                        'body': body[:2000] if body else '',
                    })
                except:
                    pass
        
        page.on("response", capture_response)
        
        print("=== 1. 加载编辑器并捕获API ===")
        page.goto("https://editor.csdn.net/md/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)
        
        # ══════════════════════════════
        # 分析各个API响应
        # ══════════════════════════════
        print("\n=== 2. 分析API响应 ===")
        for resp in api_responses:
            url = resp['url']
            body = resp['body']
            print(f"\n  {resp['method']} {url[:90]}")
            print(f"  Status: {resp['status']}")
            
            if body and body.startswith('{'):
                try:
                    data = json.loads(body)
                    # Print structure (keys only for large)
                    if isinstance(data, dict):
                        for k, v in data.items():
                            if isinstance(v, (str, int, float, bool)):
                                print(f"    {k}: {v}")
                            elif isinstance(v, list) and len(v) < 10:
                                print(f"    {k}: {v}")
                            elif isinstance(v, dict):
                                print(f"    {k}: (dict with {len(v)} keys)")
                                for k2, v2 in v.items():
                                    if isinstance(v2, (str, int, float, bool)):
                                        print(f"      {k2}: {v2}")
                                    elif isinstance(v2, list):
                                        print(f"      {k2}: [{len(v2)} items]")
                                        for item in v2[:3]:
                                            if isinstance(item, dict):
                                                print(f"        {json.dumps(item, ensure_ascii=False)[:150]}")
                                            else:
                                                print(f"        {item}")
                                    else:
                                        print(f"      {k2}: {type(v2).__name__}")
                            else:
                                print(f"    {k}: {type(v).__name__} [{len(v) if isinstance(v, (list, dict, str)) else ''}]")
                except json.JSONDecodeError:
                    print(f"    (raw, {len(body)} chars)")
        
        # ══════════════════════════════
        # 3. 查找发布按钮
        # ══════════════════════════════
        print("\n=== 3. 发布按钮和选项 ===")
        
        # Click the publish button to see options
        publish_btn = page.locator("button:has-text('发布'), button:has-text('Publish'), [class*='publish'], [class*='submit']").first
        if publish_btn.count() > 0 and publish_btn.is_visible():
            pub_text = publish_btn.inner_text()
            print(f"  发布按钮: {pub_text}")
            
            # Click to see dropdown
            publish_btn.click()
            page.wait_for_timeout(2000)
            page.screenshot(path="/tmp/csdn_explore_05_publish.png")
            
            # Check what appeared
            dropdowns = page.locator("[class*='dropdown'], [class*='popup'], [class*='menu'], [class*='dialog']").first
            if dropdowns.is_visible():
                print(f"  弹出内容: {dropdowns.inner_text()[:300]}")
        else:
            print("  ⚠️ 未找到发布按钮")
            # Print all buttons
            all_btns = page.locator("button")
            for i in range(all_btns.count()):
                if all_btns.nth(i).is_visible():
                    print(f"  按钮[{i}]: {all_btns.nth(i).inner_text()[:40]}")
        
        # ══════════════════════════════
        # 4. 寻找文章分类
        # ══════════════════════════════
        print("\n=== 4. 文章分类/标签 ===")
        
        # Look for category/tag selectors
        category_elements = page.locator("[class*='cate'], [class*='tag'], [class*='type'], [class*='sort'], [class*='category'], [class*='label'], select").first
        if category_elements.count() > 0 and category_elements.is_visible():
            print(f"  分类元素: {category_elements.inner_text()[:200]}")
        
        # Check the API response for editModel/findPublicShowEditModels
        for resp in api_responses:
            if 'findPublicShowEditModels' in resp['url']:
                print("\n  📂 文章分类/模型数据:")
                if resp['body']:
                    try:
                        data = json.loads(resp['body'])
                        print(f"  {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
                    except:
                        print(f"  {resp['body'][:500]}")
        
        # Check write-active/list
        for resp in api_responses:
            if 'write-active/list' in resp['url']:
                print("\n  📝 写作活动数据:")
                if resp['body']:
                    try:
                        data = json.loads(resp['body'])
                        print(f"  {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
                    except:
                        print(f"  {resp['body'][:500]}")
        
        # Check getBaseInfo
        for resp in api_responses:
            if 'getBaseInfo' in resp['url']:
                print("\n  ℹ️ 编辑器基础信息:")
                if resp['body']:
                    try:
                        data = json.loads(resp['body'])
                        print(f"  {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
                    except:
                        print(f"  {resp['body'][:500]}")
        
        # Check get-config
        for resp in api_responses:
            if 'get-config' in resp['url']:
                print("\n  ⚙️ 编辑器配置:")
                if resp['body']:
                    try:
                        data = json.loads(resp['body'])
                        print(f"  {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
                    except:
                        print(f"  {resp['body'][:500]}")
        
        # Check list-permission
        for resp in api_responses:
            if 'list-permission' in resp['url']:
                print("\n  🔑 用户权限:")
                if resp['body']:
                    try:
                        data = json.loads(resp['body'])
                        print(f"  {json.dumps(data, ensure_ascii=False, indent=2)[:1000]}")
                    except:
                        print(f"  {resp['body'][:300]}")
        
        # ══════════════════════════════
        # 5. 查看文章管理页的分类
        # ══════════════════════════════
        print("\n=== 5. 文章管理页 ===")
        page.goto("https://mp.csdn.net/mp_blog/manage/article")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(5000)
        page.screenshot(path="/tmp/csdn_explore_06_manage_articles.png")
        
        manage_html = page.content()
        
        # Find category filters
        filters = re.findall(r'<select[^>]*>.*?</select>', manage_html, re.DOTALL)
        print(f"  管理页下拉框: {len(filters)}")
        for sel in filters[:10]:
            name = re.search(r'name=\"([^\"]+)\"', sel)
            options = re.findall(r'<option[^>]*value=\"([^\"]*)\"[^>]*>([^<]+)</option>', sel)
            n = name.group(1) if name else 'unnamed'
            print(f"    <select name={n}> ({len(options)} options)")
            for val, text in options[:10]:
                print(f"      {val}: {text}")
        
        # Find status/type filters
        status_btns = re.findall(r'已发布|草稿|审核中|回收站|原创|转载|翻译', manage_html)
        print(f"\n  文章状态关键词: {set(status_btns)}")
        
        # Find article list
        articles = re.findall(r'class=\"[^\"]*article[^\"]*\"|class=\"[^\"]*blog[^\"]*\"|class=\"[^\"]*item[^\"]*\"', manage_html)
        print(f"\n  文章列表元素: {len(articles)}")
        
        browser.close()
        print("\n✅✅✅ CSDN 深度探索完成")

if __name__ == "__main__":
    explore_csdn_deep()
