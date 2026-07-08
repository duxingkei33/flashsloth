"""E2E 验证: amobbs + mydigit 登录 + asyncio 修复"""
import sys, os, time, json, base64
sys.path.insert(0, os.path.dirname(__file__))

def test_platform(platform, site_url, label):
    """测试单个平台登录流程"""
    from plugins.amobbs_login import AmobbsPlaywrightLogin
    print(f"\n{'='*60}")
    print(f"测试: {label} ({platform})")
    print(f"{'='*60}")
    
    inst = AmobbsPlaywrightLogin(site_url=site_url, platform=platform)
    
    # 1. login/start
    print(f"[1] 启动登录...")
    result = inst.login("test_user", "test_pass")
    print(f"  success: {result.get('success')}")
    print(f"  needs_captcha: {result.get('needs_captcha')}")
    print(f"  captcha_type: {result.get('captcha_type')}")
    print(f"  error: {result.get('error', '')[:80]}")
    
    if result.get("image"):
        img_data = base64.b64decode(result["image"])
        fname = f"/tmp/{platform}_captcha.png"
        with open(fname, "wb") as f:
            f.write(img_data)
        print(f"  验证码: {fname} ({len(img_data)} bytes)")
    
    if not result.get("needs_captcha"):
        print(f"  ⚠️ 不需要验证码")
        inst.close()
        return True
    
    # 2. submit captcha (wrong code)
    print(f"[2] 提交错误验证码...")
    captcha_result = inst.submit_text_captcha("0000")
    print(f"  error: {captcha_result.get('error', '')}")
    print(f"  message: {captcha_result.get('message', '')}")
    
    # 3. close and retry (simulate 2nd attempt)
    print(f"[3] 关闭并重新登录（模拟第2次尝试）...")
    inst.close()
    inst2 = AmobbsPlaywrightLogin(site_url=site_url, platform=platform)
    result2 = inst2.login("test_user", "test_pass")
    print(f"  needs_captcha: {result2.get('needs_captcha')}")
    print(f"  error: {result2.get('error', '')[:80]}")
    
    captcha_result2 = inst2.submit_text_captcha("BBBB")
    print(f"  error: {captcha_result2.get('error', '')}")
    print(f"  message: {captcha_result2.get('message', '')}")
    
    inst2.close()
    
    # Check for asyncio error
    if "asyncio" in str(captcha_result.get('error', '')).lower():
        print(f"  ❌ ASYNCIO ERROR!")
        return False
    if "asyncio" in str(captcha_result2.get('error', '')).lower():
        print(f"  ❌ ASYNCIO ERROR!")
        return False
    
    print(f"  ✅ {label} 测试通过")
    return True


# Test both platforms
ok1 = test_platform("amobbs", "https://www.amobbs.com", "Amobbs")
ok2 = test_platform("mydigit", "https://www.mydigit.cn", "Mydigit")

print(f"\n{'='*60}")
print(f"结果: Amobbs={'✅' if ok1 else '❌'} Mydigit={'✅' if ok2 else '❌'}")
print(f"{'='*60}")