"""E2E 测试：账号编辑页是否报错"""
import re, time, sqlite3
from playwright.sync_api import sync_playwright

FS_URL = "http://localhost:5000"
ADMIN_USER = "admin_redacted"
ADMIN_PASS = "aA123456"

def test_account_edit():
    print("=== 账号编辑页 E2E 测试 ===")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        # Login
        print("\n1. 登录 FS...")
        page.goto(f"{FS_URL}/login")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='username']", ADMIN_USER)
        page.fill("input[name='password']", ADMIN_PASS)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        print(f"  ✅ 登录成功: {page.url}")
        
        # Go to accounts page
        print("\n2. 打开账号管理页...")
        page.goto(f"{FS_URL}/accounts")
        page.wait_for_load_state("networkidle")
        page.screenshot(path="/tmp/fs_bug_accounts_list.png")
        account_html = page.content()
        print(f"  ✅ 账号列表加载成功")
        
        # Find all edit links
        edit_links = page.locator("a[href*='/accounts/edit/'], a[href*='/account/edit/'], a[href*='/edit/']")
        print(f"  Found {edit_links.count()} edit links")
        
        # Check for error messages on the page
        errors = re.findall(r'错误|Error|error|500|404|Traceback|报错', account_html)
        if errors:
            print(f"  ⚠️ 页面已有错误: {errors}")
        
        # Click each edit link and check for errors
        for i in range(edit_links.count()):
            link = edit_links.nth(i)
            href = link.get_attribute("href")
            text = link.inner_text()[:30]
            print(f"\n3.{i+1} 点击编辑: {href} ({text})")
            
            # Click and capture any errors
            try:
                # Get URL directly to avoid click issues
                full_url = f"{FS_URL}{href}" if href.startswith("/") else href
                page.goto(full_url)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2000)
                
                edit_html = page.content()
                page.screenshot(path=f"/tmp/fs_bug_account_edit_{i}.png")
                
                # Check for errors
                error_patterns = [
                    '500', '404', 'Traceback', 'Internal Server Error',
                    '错误', '报错', 'Error', 'except', 'alert_error',
                ]
                found_errors = []
                for pat in error_patterns:
                    if pat in edit_html:
                        found_errors.append(pat)
                
                if found_errors:
                    print(f"  ❌ 发现错误: {found_errors}")
                    # Print error context
                    for pat in ['Traceback', 'Internal Server Error', 'alert_error']:
                        if pat in edit_html:
                            idx = edit_html.index(pat)
                            print(f"  Context: ...{edit_html[max(0,idx-200):idx+300]}...")
                else:
                    print(f"  ✅ 编辑页加载正常 (URL: {page.url})")
                
                # Print page title
                title_m = re.search(r'<title>(.*?)</title>', edit_html)
                if title_m:
                    print(f"  页面标题: {title_m.group(1)}")
                
            except Exception as e:
                print(f"  ❌ 访问异常: {e}")
        
        # Also try the accounts API if available
        print("\n4. 尝试API端点...")
        try:
            page.goto(f"{FS_URL}/api/accounts")
            page.wait_for_load_state("networkidle")
            api_html = page.content()
            if 'csrf' in api_html.lower() or 'error' in api_html.lower():
                print(f"  API可能返回错误")
            else:
                print(f"  API响应: {api_html[:200]}")
        except:
            pass
        
        browser.close()
        print("\n✅✅✅ 账号编辑测试完成")

if __name__ == "__main__":
    test_account_edit()
