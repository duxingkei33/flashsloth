"""测试发布按钮全流程"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"
USER = "admin_ohk2yp"
PASS = "test1234"

def is_real_error(url):
    """Check if URL is a real error (not localhost:5000 false positive)"""
    if "500" in url and "/5000" not in url:
        return True
    return "error" in url.lower()

def test_all():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        errors = []

        # 1. Login
        page.goto(f"{BASE}/login")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='username']", USER)
        page.fill("input[name='password']", PASS)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        assert "login" not in page.url.lower(), f"登录失败: {page.url}"
        print("✅ 1. 登录成功")

        # 2. Dashboard - find publish buttons
        page.goto(f"{BASE}/")
        page.wait_for_load_state("networkidle")
        publish_links = page.query_selector_all("a[href*='publish/select']")
        print(f"✅ 2. 仪表盘发布按钮: {len(publish_links)} 个")
        for link in publish_links:
            href = link.get_attribute("href")
            txt = link.inner_text().strip()[:30] if link.inner_text() else ""
            print(f"    href={href} text='{txt}'")

        if not publish_links:
            errors.append("仪表盘没有发布按钮")
        else:
            # 3. Click publish on first article
            first = publish_links[0]
            href0 = first.get_attribute("href")
            print(f"\n--- 3. 点击发布按钮: {href0} ---")
            first.click()
            page.wait_for_load_state("networkidle")
            print(f"   URL: {page.url}")
            print(f"   Title: {page.title()}")
            
            if is_real_error(page.url):
                print("   ❌ 发布选择页报错!")
                errors.append(f"发布按钮 {href0} 跳转错误: {page.url}")
            elif "/publish/select/" in page.url:
                print("   ✅ 正常进入发布选择页")
                # Check for account selection
                btns = page.query_selector_all("button, a.btn, input[type=submit], input[type=checkbox]")
                has_action = False
                for btn in btns:
                    txt = (btn.inner_text().strip() or btn.get_attribute("value") or "").lower()
                    href = (btn.get_attribute("href") or "").lower()
                    if "布" in txt or "publish" in href:
                        has_action = True
                        break
                if has_action:
                    print("   ✅ 有发布操作按钮")
                else:
                    print("   ⚠️ 未发现发布操作按钮")
            else:
                print(f"   ⚠️ 意外跳转: {page.url}")

        # 4. Test all articles' publish/select pages
        print("\n--- 4. 测试各文章的发布选择页面 ---")
        for art_id in [8, 9, 10, 11, 12, 13]:
            page.goto(f"{BASE}/publish/select/{art_id}")
            page.wait_for_load_state("networkidle")
            ok = "/publish/select/" in page.url and "login" not in page.url.lower()
            status = "✅" if ok else "❌"
            title = page.title()[:60]
            print(f"   {status} article/{art_id}: {title}")
            if not ok:
                errors.append(f"文章 {art_id} 发布选择页异常: {page.url}")
            else:
                # Check for 500 flash message in body
                body = page.inner_text("body")
                if "Internal Server Error" in body or "500" in body[:200]:
                    errors.append(f"文章 {art_id} 页面内容含500错误")
                    print(f"       ⚠️ 页面内容异常!")

        # 5. Publish manage page
        print("\n--- 5. 发布管理页面 ---")
        page.goto(f"{BASE}/publish/manage")
        page.wait_for_load_state("networkidle")
        if "/publish/manage" in page.url:
            print(f"   ✅ 正常: {page.title()}")
            # Check refresh button
            refresh_btn = page.query_selector("#refreshPendingBtn")
            if refresh_btn:
                print(f"   ✅ 刷新按钮存在: {refresh_btn.inner_text().strip()}")
            else:
                errors.append("发布管理页缺少刷新按钮")
            
            # Check pending_review display
            body_text = page.inner_text("body")
            if "待审核" in body_text:
                print(f"   ✅ 待审核状态标签正常显示")
            else:
                print(f"   ℹ️ 当前无待审核状态")
        else:
            errors.append(f"发布管理页异常: {page.url}")
            print("   ❌ 异常跳转")

        # 6. Deployers page
        print("\n--- 6. 部署器页面 ---")
        page.goto(f"{BASE}/deployers")
        page.wait_for_load_state("networkidle")
        if "/deployers" in page.url:
            print(f"   ✅ 正常: {page.title()}")
        else:
            errors.append(f"部署器页异常: {page.url}")
            print("   ❌ 异常跳转")

        # 7. Test the actual publish endpoint
        print("\n--- 7. 测试发布 API 端点 ---")
        # Check POST to /publish
        page.goto(f"{BASE}/publish/select/8")
        page.wait_for_load_state("networkidle")
        
        # Find account checkboxes and submit button
        checkboxes = page.query_selector_all("input[type='checkbox']")
        print(f"   账号选择框: {len(checkboxes)} 个")
        for cb in checkboxes:
            name = cb.get_attribute("name") or ""
            val = cb.get_attribute("value") or ""
            print(f"     name={name} value={val[:30]}")
        
        # Find the form submit action
        forms = page.query_selector_all("form")
        print(f"   表单: {len(forms)} 个")
        for form in forms:
            action = form.get_attribute("action") or ""
            method = form.get_attribute("method") or ""
            print(f"     action={action} method={method}")

        browser.close()
        
        print(f"\n{'='*50}")
        if errors:
            print(f"❌ 发现 {len(errors)} 个问题:")
            for e in errors:
                print(f"   - {e}")
        else:
            print("✅ 全部页面正常！")
        
        return errors

if __name__ == "__main__":
    test_all()
