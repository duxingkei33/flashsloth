"""Playwright: 测试发布按钮全流程，发现具体错误"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from playwright.sync_api import sync_playwright
import json

BASE = "http://localhost:5000"

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        
        # Login
        page.goto(f"{BASE}/login")
        page.fill("input[name='username']", "admin_ohk2yp")
        page.fill("input[name='password']", "test1234")
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")
        print(f"1. 登录: {page.url}")
        
        # Dashboard - click first publish button
        page.goto(f"{BASE}/")
        page.wait_for_load_state("networkidle")
        
        pub_links = page.query_selector_all("a[href*='publish/select']")
        print(f"2. 发布按钮数: {len(pub_links)}")
        
        for link in pub_links:
            href = link.get_attribute("href")
            txt = link.inner_text().strip()
            print(f"   href={href} text='{txt}'")
        
        # Click first publish button
        if pub_links:
            href = pub_links[0].get_attribute("href")
            print(f"\n3. 点击: {href}")
            
            # Listen for console errors
            errors_before = []
            page.on("console", lambda msg: errors_before.append(f"[{msg.type}] {msg.text}") if msg.type in ("error",) else None)
            page.on("pageerror", lambda err: errors_before.append(f"[PAGE_ERROR] {err}"))
            
            pub_links[0].click()
            page.wait_for_load_state("networkidle")
            
            print(f"   URL: {page.url}")
            print(f"   Title: {page.title()}")
            
            # Check for errors
            if errors_before:
                print(f"   ❌ Console errors:")
                for e in errors_before:
                    print(f"      {e}")
            
            page_text = page.inner_text("body")[:600]
            print(f"   Page text: {page_text[:300]}")
            
            # Check for server errors
            if "Internal Server Error" in page_text or "500" in page_text[:100]:
                print(f"   ❌ SERVER ERROR 500!")
        
        # Now test each article's publish select page
        print(f"\n4. 逐个测试文章发布页面:")
        for aid in [8, 9, 10, 11, 12, 13]:
            resp = page.goto(f"{BASE}/publish/select/{aid}")
            page.wait_for_load_state("networkidle")
            status_code = resp.status if resp else "?"
            print(f"   article/{aid}: HTTP {status_code} -> {page.url.split('?')[0]}")
            
            body = page.inner_text("body")
            if "Internal Server Error" in body:
                print(f"      ❌ 500 ERROR!")
            elif "publish/select" not in page.url:
                print(f"      ❌ 重定向到: {page.url}")
        
        # Test the publish POST
        print(f"\n5. 测试发布表单提交:")
        page.goto(f"{BASE}/publish/select/8")
        page.wait_for_load_state("networkidle")
        
        # Check form
        form = page.query_selector("form")
        if form:
            action = form.get_attribute("action")
            print(f"   Form action: {action}")
            
            # Try to submit with no accounts selected
            form.evaluate("f => f.submit()")
            page.wait_for_load_state("networkidle")
            print(f"   Submit result URL: {page.url}")
            body2 = page.inner_text("body")[:500]
            print(f"   Body: {body2[:200]}")
        else:
            print(f"   ❌ No form found!")
        
        # Test dashboard publish button for article 26 (test article that may not exist)
        print(f"\n6. 测试文章26（可能已删除）:")
        resp = page.goto(f"{BASE}/publish/select/26")
        page.wait_for_load_state("networkidle")
        status_code = resp.status if resp else "?"
        print(f"   HTTP {status_code} -> {page.url}")
        body3 = page.inner_text("body")[:400]
        print(f"   Body: {body3[:200]}")
        
        browser.close()
        print(f"\n✅ 测试完成")

test()
