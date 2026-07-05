"""CSDN 微信扫码登录 v2 — 二维码放FS页面供扫码"""
import re, json, time, os, sys, base64
from playwright.sync_api import sync_playwright

FS_URL = "http://localhost:5000"
FS_STATIC = "/home/duxingkei/.hermes/flashsloth/static"

def csdn_qrcode_login():
    print("=== CSDN 微信扫码登录 ===")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        print("\n1. 打开 CSDN 登录页...")
        page.goto("https://passport.csdn.net/login")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(3000)
        
        print("\n2. 切换到微信登录...")
        wechat_tab = page.locator("text=微信登录").first
        if wechat_tab.is_visible():
            wechat_tab.click()
            page.wait_for_timeout(2000)
        
        # Step 3: Extract QR code and serve via FS
        print("\n3. 提取二维码并发布到FS...")
        qr_img = page.locator("img").first
        # Find the QR code image by looking for base64 or large images
        all_imgs = page.locator("img")
        qr_src = None
        for i in range(all_imgs.count()):
            src = all_imgs.nth(i).get_attribute("src") or ""
            if "base64" in src and len(src) > 500:
                qr_src = src
                print(f"  找到二维码图片 (index={i}, len={len(src)})")
                break
        
        if qr_src:
            b64_data = qr_src.split(",")[1]
            img_data = base64.b64decode(b64_data)
            qr_path = os.path.join(FS_STATIC, "csdn_qrcode.png")
            with open(qr_path, "wb") as f:
                f.write(img_data)
            print(f"  ✅ 二维码已保存到: {qr_path}")
            
            # Create an HTML page to display the QR code
            html_content = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CSDN 微信扫码登录</title>
<style>
body {{ display:flex; justify-content:center; align-items:center; min-height:80vh; background:#f0f2f5; font-family:sans-serif; }}
.card {{ background:white; padding:40px; border-radius:16px; box-shadow:0 4px 20px rgba(0,0,0,.1); text-align:center; max-width:400px; }}
.qr {{ width:280px; height:280px; margin:20px auto; }}
.qr img {{ width:100%; height:100%; }}
.status {{ font-size:18px; margin:16px 0; }}
.loading {{ color:#666; }}
.success {{ color:#52c41a; }}
.refresh-btn {{ padding:8px 24px; border:1px solid #4361ee; border-radius:8px; background:white; color:#4361ee; cursor:pointer; font-size:14px; }}
</style></head><body>
<div class="card">
    <h2>📱 CSDN 微信扫码登录</h2>
    <p style="color:#666;">请打开微信「扫一扫」扫描下方二维码</p>
    <div class="qr"><img src="/static/csdn_qrcode.png" alt="CSDN QR Code" id="qr_img"></div>
    <div class="status loading" id="status">⏳ 等待扫码...</div>
    <p style="font-size:12px;color:#999;">扫码后页面会自动刷新</p>
    <button class="refresh-btn" onclick="location.reload()">🔄 刷新二维码</button>
</div>
<script>
// Auto refresh to check if QR code needs update
setTimeout(function() {{
    var img = document.getElementById('qr_img');
    img.src = '/static/csdn_qrcode.png?t=' + Date.now();
}}, 30000);
</script>
</body></html>"""
            qr_html_path = os.path.join(FS_STATIC, "csdn_login.html")
            with open(qr_html_path, "w") as f:
                f.write(html_content)
            
            print(f"  ✅ 登录页已创建: {qr_html_path}")
            print(f"\n{'='*60}")
            print(f"  🌐 请用浏览器访问: http://103.97.178.234:5001/static/csdn_login.html")
            print(f"  📱 然后用微信扫页面上的二维码登录CSDN")
            print(f"{'='*60}")
        else:
            # Fallback: use page screenshot
            page.screenshot(path=os.path.join(FS_STATIC, "csdn_qrcode.png"))
            print("  ⚠️ 使用页面截图，二维码在截图内")
        
        # Step 4: Poll for login
        print("\n4. 等待扫码登录（最长5分钟）...")
        max_wait = 300
        start = time.time()
        logged_in = False
        
        while time.time() - start < max_wait:
            time.sleep(5)
            url = page.url
            
            if "passport.csdn.net" not in url and "login" not in url.lower():
                logged_in = True
                print(f"\n  ✅ 登录成功! 跳转到: {url}")
                break
            
            # Check for QR code refresh (CSDN rotates QR codes)
            elapsed = int(time.time() - start)
            if elapsed % 30 == 0:
                # Re-extract QR code in case it refreshed
                try:
                    new_qr = page.locator("img[src*='base64']").first
                    if new_qr.count() > 0:
                        new_src = new_qr.get_attribute("src")
                        if new_src and "base64" in new_src:
                            b64 = new_src.split(",")[1]
                            img_data = base64.b64decode(b64)
                            with open(qr_path, "wb") as f:
                                f.write(img_data)
                            print(f"  [{elapsed}s] 二维码已刷新")
                except:
                    pass
            
            if elapsed % 60 == 0:
                remaining = int((max_wait - (time.time() - start)) / 60)
                print(f"  [{elapsed}s] 还剩约{remaining}分钟...")
        
        if not logged_in:
            print("  ❌ 登录超时 (5分钟)")
            # Clean up temp files
            for f in ["csdn_qrcode.png", "csdn_login.html"]:
                p = os.path.join(FS_STATIC, f)
                if os.path.exists(p):
                    os.remove(p)
            browser.close()
            return False
        
        # Step 5: Save cookies
        print("\n5. 保存Cookie到FS数据库...")
        cookies = context.cookies()
        cookie_parts = []
        for c in cookies:
            domain = c.get('domain', '')
            if 'csdn' in domain:
                cookie_parts.append(f"{c['name']}={c['value']}")
        
        cookie_str = "; ".join(cookie_parts)
        print(f"  Cookie长度: {len(cookie_str)}")
        
        if not cookie_str:
            print("  ❌ Cookie为空")
            browser.close()
            return False
        
        import sqlite3
        conn = sqlite3.connect('/home/duxingkei/.hermes/flashsloth/flashsloth.db')
        existing = conn.execute(
            "SELECT id FROM platform_accounts WHERE platform='csdn' AND user_id=1"
        ).fetchone()
        
        config = json.dumps({
            "login_mode": "qrcode",
            "site_url": "https://www.csdn.net",
            "cookie": cookie_str,
        })
        
        if existing:
            conn.execute(
                "UPDATE platform_accounts SET config_json=?, is_active=1 WHERE id=?",
                (config, existing[0])
            )
            print(f"  ✅ CSDN账户(ID={existing[0]}) Cookie已更新")
        else:
            conn.execute(
                "INSERT INTO platform_accounts (user_id, platform, account_name, config_json, is_active) VALUES (?,?,?,?,?)",
                (1, "csdn", "duxingkei@csdn", config, 1)
            )
            print("  ✅ 新CSDN账户已创建")
        conn.commit()
        conn.close()
        
        # Step 6: Verify
        print("\n6. 验证登录...")
        verify_ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        for c in cookies:
            if 'csdn' in c.get('domain', ''):
                verify_ctx.add_cookies([c])
        
        vp = verify_ctx.new_page()
        vp.goto("https://www.csdn.net/")
        vp.wait_for_load_state("networkidle")
        vp.wait_for_timeout(2000)
        
        vp_html = vp.content()
        if '退出' in vp_html or 'duxingkei' in vp_html.lower():
            print("  ✅ CSDN登录验证成功!")
        else:
            print("  ⚠️ 登录状态待确认")
            vp.screenshot(path="/tmp/csdn_verify.png")
        
        verify_ctx.close()
        
        # Cleanup temp files
        for f in ["csdn_qrcode.png", "csdn_login.html"]:
            p = os.path.join(FS_STATIC, f)
            if os.path.exists(p):
                os.remove(p)
                print(f"  🧹 临时文件已清理: {f}")
        
        browser.close()
        print("\n✅✅✅ CSDN 登录完成!")
        return True

if __name__ == "__main__":
    success = csdn_qrcode_login()
    if not success:
        print("\n❌ 登录失败")
        sys.exit(1)
