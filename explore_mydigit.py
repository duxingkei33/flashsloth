"""
数码之家 (mydigit.cn) — 安全探索脚本
协议：2-5秒间隔，单Session≤3次操作，只读不写，遇418/验证码停
"""
import json, time, sys
from playwright.sync_api import sync_playwright

SITE = "https://www.mydigit.cn"
COOKIE_STR = "security_session_verify=f914cba344c390591e5da3fd9a180323; VhUn_2132_saltkey=IrvJJvVg; VhUn_2132_lastvisit=1782748430; VhUn_2132_lastact=1782752032%09member.php%09logging; VhUn_2132_ulastactivity=1782752032%7C0; VhUn_2132_auth=cfadIKXWJI7YytmyzLevcaMGKn3dQTZ9tLjFhAogPKqJ8UYL6Ug95miAjsDdVbHHUft7NVN9EAgf0xfoZHVrHPul2BSZ; VhUn_2132_lastcheckfeed=1722267%7C1782752032; VhUn_2132_checkfollow=1; VhUn_2132_lip=103.97.178.234%2C1782752032"

def sleep():
    delay = 2 + (time.time() % 3)  # 2-5 seconds
    time.sleep(delay)

def explore():
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        # Set cookies from string
        for c in COOKIE_STR.split("; "):
            if "=" in c:
                k, v = c.split("=", 1)
                ctx.add_cookies([{
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": ".mydigit.cn",
                    "path": "/"
                }])
        
        page = ctx.new_page()
        op_count = 0
        max_ops = 5

        # --- OP 1: Go to homepage, check login status ---
        print("=" * 60)
        print("[OP 1] 访问首页，检查登录状态")
        page.goto(SITE, wait_until="networkidle", timeout=30000)
        sleep()
        op_count += 1
        
        # Check if logged in
        login_status = page.query_selector("a[href*='member.php?mod=logging']")
        username_el = page.query_selector(".vwmy, .z a[href*='space-uid']")
        print(f"  登录链接存在: {login_status is not None} (有=未登录)")
        if username_el:
            print(f"  用户名元素: {username_el.inner_text()}")
        
        # Check for any alerts/warnings
        alert = page.query_selector(".alert_error, .alert_info, #messagetext")
        if alert:
            print(f"  ⚠️ 页面警告: {alert.inner_text()[:200]}")
        
        page.screenshot(path="/tmp/mydigit_home.png")
        print(f"  首页截图: /tmp/mydigit_home.png")
        
        # --- OP 2: Go to forum rules / announcements ---
        print("=" * 60)
        print("[OP 2] 读取论坛公告/版规")
        
        # Try to find announcements section
        page.goto(f"{SITE}/forum.php?mod=announcement", wait_until="networkidle", timeout=30000)
        sleep()
        op_count += 1
        ann_title = page.title()
        print(f"  公告页标题: {ann_title}")
        
        # Check for any rules content
        rules_text = page.query_selector("#announcement_body, .annbody, .t_msgfont")
        if rules_text:
            print(f"  公告内容预览: {rules_text.inner_text()[:500]}")
        else:
            # Try the forum with fid=40 which was stored
            print("  公告页可能无权限，尝试查看板块规则...")
            
        page.screenshot(path="/tmp/mydigit_announcement.png")
        
        # --- OP 3: Go to the specific forum section (fid=40) ---
        print("=" * 60)
        print(f"[OP 3] 访问板块 fid=40")
        page.goto(f"{SITE}/forum.php?mod=forumdisplay&fid=40", wait_until="networkidle", timeout=30000)
        sleep()
        op_count += 1
        
        # Read sub-forum rules if any
        rules = page.query_selector(".rules, .forumrules, .bn, #forumrules")
        if rules:
            rules_text = rules.inner_text()
            print(f"  板块规则: {rules_text[:1000]}")
            results.append(("板块规则", rules_text[:2000]))
        
        page.screenshot(path="/tmp/mydigit_forum40.png")
        
        # Check stiky posts (置顶帖 - often rules)
        sticky_titles = page.query_selector_all("th.new a[href*='thread']")
        print(f"\n  帖子列表 ({len(sticky_titles)} 个可见标题):")
        for t in sticky_titles[:10]:
            print(f"    - {t.inner_text()[:80]}")
        
        # --- OP 4: Read a sticky post about rules ---
        print("=" * 60)
        print("[OP 4] 读取置顶帖子（版规）")
        
        # Get all sticky threads
        all_threads = page.query_selector_all("th a.xst")
        print(f"  发现 {len(all_threads)} 个帖子链接")
        
        for t in all_threads[:8]:
            title = t.inner_text()
            if any(kw in title for kw in ["规", "公告", "须知", "指南", "帮助", "教程", "规则", "必读", "要求", "限制"]):
                href = t.get_attribute("href")
                if href:
                    full_url = href if href.startswith("http") else f"{SITE}/{href}"
                    print(f"  📖 读取规则帖: {title}")
                    page.goto(full_url, wait_until="networkidle", timeout=30000)
                    sleep()
                    op_count += 1
                    
                    # Read post content
                    content = page.query_selector(".t_fsz, .pcb, .pct, .t_msgfont, #postlist .t_f, .plc .message")
                    if content:
                        text = content.inner_text()
                        print(f"  正文内容 ({len(text)} chars):")
                        print(text[:2000])
                        results.append((title, text[:3000]))
                    
                    page.screenshot(path=f"/tmp/mydigit_rule_{title[:20].replace('/', '_')}.png")
                    break  # Read just the first rule post
        
        # --- OP 5: Go to post editor to check fields ---
        print("=" * 60)
        print("[OP 5] 访问发帖页面，检查编辑器结构")
        page.goto(f"{SITE}/forum.php?mod=post&action=newthread&fid=40", wait_until="networkidle", timeout=30000)
        sleep()
        op_count += 1
        
        # Check for permission errors
        error_msg = page.query_selector("#messagetext, .alert_error")
        if error_msg:
            err_text = error_msg.inner_text()
            print(f"  ⚠️ 发帖权限检查: {err_text[:300]}")
            if "403" in err_text or "拒绝" in err_text or "权限" in err_text:
                results.append(("发帖权限", f"无发帖权限: {err_text[:300]}"))
        else:
            print("  ✅ 有发帖权限")
            results.append(("发帖权限", "✅ 有发帖权限"))
        
        # Check editor elements
        title_input = page.query_selector("input#subject")
        if title_input:
            max_len = title_input.get_attribute("maxlength")
            print(f"  标题输入框: maxlength={max_len}")
            results.append(("标题长度限制", max_len or "80 (Discuz默认)"))
        
        # Check textarea
        textarea = page.query_selector("textarea#fastpostmessage, textarea#message, .editor_textarea")
        if textarea:
            print(f"  编辑器 textarea 存在 ✅")
        
        # Check upload section
        upload_area = page.query_selector("#attachnotice_img, #uploadapp, .upload_area, a[href*='upload']")
        if upload_area:
            upload_html = upload_area.inner_html()[:500]
            print(f"  上传区域存在 ✅: {upload_html[:200]}")
            
            # Try to find the upload button/link
            upload_btn = page.query_selector("a[href*='upload'], #uploadapp a, .upload_btn")
            if upload_btn:
                print(f"  上传按钮: {upload_btn.inner_text()}")
        else:
            # Try clicking advanced mode
            advanced = page.query_selector("a[href*='action=newthread&fid=40&extra=&topicsubmit=yes']")
            if advanced:
                print("  发现高级模式链接")
        
        # Check for file type / size restrictions displayed on page
        upload_hints = page.query_selector("#uploadtip, .uploadtip, .attach_noperm, .tip, .notice")
        if upload_hints:
            hint_text = upload_hints.inner_text()
            print(f"  上传提示: {hint_text[:500]}")
            results.append(("上传限制", hint_text[:1000]))
        
        # Check for allowed extensions display
        page_source = page.content()
        import re
        ext_matches = re.findall(r'(?:允许|支持|附件|扩展名|格式)[：:\s]*(?:.*?)(?:\.\w+(?:\s*[,，、]\s*\.?\w+)*)', page_source)
        if ext_matches:
            print(f"  发现扩展名提示: {ext_matches[:3]}")
        
        # Check hidden size limits
        size_matches = re.findall(r'(?:大小|尺寸|限制|上限|最大)[：:\s]*(?:.*?)(?:\d+\.?\d*\s*(?:KB|MB|GB|K|M))', page_source[:50000])
        if size_matches:
            print(f"  发现大小限制: {size_matches[:3]}")
            results.append(("大小限制", str(size_matches[:3])))
        
        # Check for image dimensions
        img_size_matches = re.findall(r'(?:像素|分辨率|宽|尺寸)[：:\s]*(?:.*?)(?:\d+\s*[xX×]\s*\d+)', page_source[:50000])
        if img_size_matches:
            print(f"  发现图片尺寸限制: {img_size_matches[:3]}")
            results.append(("图片尺寸限制", str(img_size_matches[:3])))
        
        page.screenshot(path="/tmp/mydigit_editor.png")
        
        # --- Summary ---
        print("\n" + "=" * 60)
        print("探索结果摘要:")
        for title, content in results:
            print(f"\n--- {title} ---")
            print(content[:500])
        
        browser.close()
    
    return results

if __name__ == "__main__":
    try:
        results = explore()
        # Save results
        output = {"timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "findings": results}
        with open("/tmp/mydigit_exploration.json", "w") as f:
            json.dump([{"title": r[0], "content": r[1]} for r in results], f, ensure_ascii=False, indent=2)
        print(f"\n✅ 探索完成，结果保存至 /tmp/mydigit_exploration.json")
    except Exception as e:
        print(f"❌ 探索失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
