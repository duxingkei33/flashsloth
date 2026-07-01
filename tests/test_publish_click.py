"""Playwright: 测试发布记录标题 + 发布按钮"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5000"

def main():
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()

        # Login
        page.goto(f"{BASE}/login")
        page.wait_for_load_state("networkidle")
        page.fill("input[name='username']", "admin_ohk2yp")
        page.fill("input[name='password']", "test1234")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        assert "login" not in page.url.lower(), "登录失败"
        print("✅ 1. 登录成功")

        # Dashboard - check publish records table
        page.goto(f"{BASE}/")
        page.wait_for_load_state("networkidle")
        html = page.content()

        # Check article title exists in publish records
        articles_in_logs = ['咸鱼淘了两个网关', 'Hello World', 'FlashSloth 正式上线', 'FlashSloth', '测试文章', '墨水屏价签']
        found_titles = []
        for title in articles_in_logs:
            if title in html:
                found_titles.append(title)
        print(f"✅ 2. 发布记录显示文章标题: {len(found_titles)}/{len(articles_in_logs)} 匹配")

        # Check they're linked to edit page
        for title in articles_in_logs:
            # Look for href containing the title
            import re
            pattern = r'href="/post/edit/\d+"[^>]*>' + re.escape(title[:10])
            if re.search(pattern, html):
                print(f"   ✅ 标题可点击: '{title[:20]}...'")
            else:
                errors.append(f"标题未链接到编辑页: {title[:20]}")
                print(f"   ❌ 标题未链接: '{title[:20]}...'")

        # Test publish button - article 8
        print(f"\n3. 测试发布按钮 → /publish/select/8")
        resp = page.goto(f"{BASE}/publish/select/8")
        page.wait_for_load_state("networkidle")
        if "/publish/select/8" in page.url:
            print(f"   ✅ 正常访问发布选择页")
            # Check for form
            form = page.query_selector("form[action='/publish']")
            if form:
                print(f"   ✅ 发布表单存在")
                cbs = page.query_selector_all("input[type='checkbox'][name='account_ids']")
                print(f"   ✅ 账号选择框: {len(cbs)} 个")
                sub_btn = page.query_selector("#publishBtn")
                if sub_btn:
                    print(f"   ✅ 发布提交按钮存在: '{sub_btn.inner_text().strip()}'")
            else:
                errors.append("发布选择页缺少表单")
                print(f"   ❌ 无发布表单")
        else:
            errors.append(f"发布按钮跳转异常: {page.url}")
            print(f"   ❌ 跳转异常: {page.url}")

        # Test article 26 too
        print(f"\n4. 测试文章26发布选择页")
        resp = page.goto(f"{BASE}/publish/select/26")
        page.wait_for_load_state("networkidle")
        if "/publish/select/26" in page.url:
            print(f"   ✅ 正常")
        else:
            errors.append(f"文章26发布页异常: {page.url}")
            print(f"   ❌ 异常: {page.url}")

        browser.close()

    print(f"\n{'='*40}")
    if errors:
        print(f"❌ {len(errors)} 个问题:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ 全部正常!")
    return errors

main()
