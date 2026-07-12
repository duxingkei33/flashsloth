"""Playwright E2E 验证 amobbs 登录全流程
模拟前端完整交互：打开登录页 → 填账号 → 获取验证码 → 提交验证码 → 检查结果
"""
import sys, os, time, json, base64
sys.path.insert(0, os.path.dirname(__file__))

def test_amobbs_login_flow():
    """端到端测试 amobbs 登录流程"""
    from playwright.sync_api import sync_playwright
    from plugins.amobbs_login import AmobbsPlaywrightLogin, _find_chromium

    print("=" * 60)
    print("Amobbs 登录 E2E 验证")
    print("=" * 60)

    # 1. 创建登录实例
    print("\n[1/5] 创建 Playwright 实例...")
    inst = AmobbsPlaywrightLogin(site_url="https://www.amobbs.com", platform="amobbs")
    print(f"  site_url: {inst.site_url}")

    # 用测试账号（错误密码 → 验证验证码检测是否正常）
    test_user = "test_user_placeholder"
    test_pass = "wrong_password_123"

    # 2. 启动登录
    print(f"\n[2/5] 启动登录: {test_user}...")
    result = inst.login(test_user, test_pass)
    print(f"  success: {result.get('success')}")
    print(f"  needs_captcha: {result.get('needs_captcha')}")
    print(f"  captcha_type: {result.get('captcha_type')}")
    print(f"  error: {result.get('error', '')[:100]}")
    print(f"  captcha_image_url: {result.get('captcha_image_url', '')[:100]}")

    if result.get("image"):
        img_size = len(result["image"])
        print(f"  image (base64): {img_size} chars")
        # 保存验证码图片
        img_data = base64.b64decode(result["image"])
        with open("/tmp/amobbs_captcha.png", "wb") as f:
            f.write(img_data)
        print(f"  验证码图片保存: /tmp/amobbs_captcha.png ({len(img_data)} bytes)")

    if not result.get("needs_captcha"):
        print("  ⚠️ 不需要验证码，直接检查登录结果")
        if result.get("logged_in"):
            print("  ✅ 已登录（无需验证码）")
        else:
            print(f"  ❌ 登录失败: {result.get('error')}")
        inst.close()
        return result

    # 3. 获取验证码截图
    print("\n[3/5] 获取验证码截图...")
    screenshot = inst.take_screenshot()
    if screenshot:
        img_data = base64.b64decode(screenshot)
        with open("/tmp/amobbs_full_page.png", "wb") as f:
            f.write(img_data)
        print(f"  全页截图: /tmp/amobbs_full_page.png ({len(img_data)} bytes)")

    # 4. 提交验证码（用错误验证码 → 测试预检是否正常）
    print("\n[4/5] 提交验证码（测试验证码=0000）...")
    captcha_result = inst.submit_text_captcha("0000")
    print(f"  success: {captcha_result.get('success')}")
    print(f"  needs_captcha: {captcha_result.get('needs_captcha')}")
    print(f"  message: {captcha_result.get('message', '')}")
    print(f"  error: {captcha_result.get('error', '')}")
    print(f"  logged_in: {captcha_result.get('logged_in')}")

    # 5. 检查结果
    print("\n[5/5] 结果分析...")
    if captcha_result.get("error") == "验证码错误":
        print("  ✅ 验证码预检正常：正确检测到验证码错误")
    elif captcha_result.get("error") == "核验未完成":
        print("  ❌ 回归BUG：验证码预检阻断提交（核验未完成）")
    elif captcha_result.get("logged_in"):
        print("  ✅ 登录成功")
    else:
        print(f"  ⚠️ 其他结果: {captcha_result.get('message')}")

    # 有验证码图片就保存
    if captcha_result.get("image"):
        img_data = base64.b64decode(captcha_result["image"])
        with open("/tmp/amobbs_result.png", "wb") as f:
            f.write(img_data)
        print(f"  结果截图: /tmp/amobbs_result.png ({len(img_data)} bytes)")

    inst.close()
    return captcha_result


if __name__ == "__main__":
    result = test_amobbs_login_flow()
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    # 最终判定
    if result.get("error") == "核验未完成":
        print("❌ FAIL: 回归BUG — 验证码预检阻断提交")
        sys.exit(1)
    elif result.get("error") == "验证码错误":
        print("✅ PASS: 验证码预检正常，错误验证码正确检测")
        sys.exit(0)
    elif result.get("logged_in"):
        print("✅ PASS: 登录成功")
        sys.exit(0)
    else:
        print(f"⚠️ WARN: 结果不确定 — {result.get('message', '')}")
        sys.exit(0)