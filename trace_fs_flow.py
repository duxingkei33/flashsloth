"""Playwright 全流程追踪：FS 前端 → 添加 amobbs 账号 → 每一步 API 调用 + 后端行为"""
import sys, os, time, json, base64, requests
sys.path.insert(0, os.path.dirname(__file__))

BASE = "http://127.0.0.1:5000"
SESSION = requests.Session()

# ═══════════════════════════════════════════════
# 0. 登录 FS
# ═══════════════════════════════════════════════
print("=" * 60)
print("0. 登录 FlashSloth")
print("=" * 60)
r = SESSION.post(f"{BASE}/login", json={
    "username": "admin_redacted",
    "password": "Fs&211211"
})
print(f"  status: {r.status_code}")
print(f"  cookies: {dict(SESSION.cookies)}")
if r.status_code != 200:
    # try form-encoded
    r = SESSION.post(f"{BASE}/login", data={
        "username": "admin_redacted",
        "password": "Fs&211211"
    })
    print(f"  form-encoded status: {r.status_code}")

# ═══════════════════════════════════════════════
# 1. 启动浏览器登录
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("1. POST /api/platform/amobbs/login/start")
print("=" * 60)
start_payload = {
    "username": "testuser_abc",
    "password": "testpass_xyz",
    "account_id": 0,
    "platform": "amobbs",
    "site_url": "https://www.amobbs.com"
}
r = SESSION.post(f"{BASE}/api/platform/amobbs/login/start", json=start_payload)
print(f"  status: {r.status_code}")
start_result = r.json()
print(f"  success: {start_result.get('success')}")
print(f"  needs_captcha: {start_result.get('needs_captcha')}")
print(f"  captcha_type: {start_result.get('captcha_type')}")
print(f"  captcha_image_url: {start_result.get('captcha_image_url', '')[:120]}")
print(f"  error: {start_result.get('error', '')[:100]}")
print(f"  logged_in: {start_result.get('logged_in')}")

if start_result.get("image"):
    img_data = base64.b64decode(start_result["image"])
    with open("/tmp/fs_trace_captcha.png", "wb") as f:
        f.write(img_data)
    print(f"  image saved: /tmp/fs_trace_captcha.png ({len(img_data)} bytes)")
else:
    print("  ❌ NO CAPTCHA IMAGE!")

# ═══════════════════════════════════════════════
# 2. 提交验证码（第1次）
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("2. POST /api/platform/amobbs/login/submit_captcha (test=AAAA)")
print("=" * 60)
r = SESSION.post(f"{BASE}/api/platform/amobbs/login/submit_captcha", json={
    "captcha_code": "AAAA",
    "account_id": 0
})
print(f"  status: {r.status_code}")
sub_result = r.json()
print(f"  success: {sub_result.get('success')}")
print(f"  needs_captcha: {sub_result.get('needs_captcha')}")
print(f"  logged_in: {sub_result.get('logged_in')}")
print(f"  error: {sub_result.get('error', '')}")
print(f"  message: {sub_result.get('message', '')}")
print(f"  captcha_verified: {sub_result.get('captcha_verified')}")

if sub_result.get("image"):
    img_data = base64.b64decode(sub_result["image"])
    with open("/tmp/fs_trace_result1.png", "wb") as f:
        f.write(img_data)
    print(f"  result image: /tmp/fs_trace_result1.png ({len(img_data)} bytes)")

# ═══════════════════════════════════════════════
# 3. 刷新验证码
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("3. POST /api/platform/amobbs/login/refresh_captcha")
print("=" * 60)
r = SESSION.post(f"{BASE}/api/platform/amobbs/login/refresh_captcha")
print(f"  status: {r.status_code}")
ref_result = r.json()
print(f"  success: {ref_result.get('success')}")
print(f"  captcha_image_url: {ref_result.get('captcha_image_url', '')[:120]}")

if ref_result.get("image"):
    img_data = base64.b64decode(ref_result["image"])
    with open("/tmp/fs_trace_captcha2.png", "wb") as f:
        f.write(img_data)
    print(f"  image saved: /tmp/fs_trace_captcha2.png ({len(img_data)} bytes)")

# ═══════════════════════════════════════════════
# 4. 提交验证码（第2次 — 刷新后）
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("4. POST /api/platform/amobbs/login/submit_captcha (test=BBBB)")
print("=" * 60)
r = SESSION.post(f"{BASE}/api/platform/amobbs/login/submit_captcha", json={
    "captcha_code": "BBBB",
    "account_id": 0
})
print(f"  status: {r.status_code}")
sub_result2 = r.json()
print(f"  success: {sub_result2.get('success')}")
print(f"  needs_captcha: {sub_result2.get('needs_captcha')}")
print(f"  logged_in: {sub_result2.get('logged_in')}")
print(f"  error: {sub_result2.get('error', '')}")
print(f"  message: {sub_result2.get('message', '')}")

# ═══════════════════════════════════════════════
# 5. 分析
# ═══════════════════════════════════════════════
print("\n" + "=" * 60)
print("5. 分析总结")
print("=" * 60)

errors = []
if not start_result.get("success"):
    errors.append(f"❌ login/start 失败: {start_result.get('error')}")
if not start_result.get("needs_captcha"):
    errors.append("❌ login/start 未返回 needs_captcha=True")
if not start_result.get("image"):
    errors.append("❌ login/start 未返回验证码图片")

# 第1次提交
if sub_result.get("error") == "验证码错误":
    print("  第1次提交: ✅ 正确返回'验证码错误'(错误验证码)")
elif sub_result.get("error") == "核验未完成":
    errors.append("❌ 第1次提交: 回归BUG — '核验未完成'阻断")
    print("  第1次提交: ❌ 回归BUG — '核验未完成'阻断")
else:
    print(f"  第1次提交: ⚠️ {sub_result.get('error') or sub_result.get('message')}")

# 刷新
if ref_result.get("success") and ref_result.get("image"):
    print("  刷新验证码: ✅ 成功")
else:
    errors.append(f"❌ 刷新验证码失败: {ref_result.get('error', '')}")

# 第2次提交
if sub_result2.get("error") == "验证码错误":
    print("  第2次提交: ✅ 正确返回'验证码错误'(错误验证码)")
elif sub_result2.get("error") == "核验未完成":
    errors.append("❌ 第2次提交: 回归BUG — '核验未完成'阻断")
    print("  第2次提交: ❌ 回归BUG — '核验未完成'阻断")
else:
    print(f"  第2次提交: ⚠️ {sub_result2.get('error') or sub_result2.get('message')}")

if errors:
    print(f"\n❌ FAIL: {len(errors)} 个问题:")
    for e in errors:
        print(f"  {e}")
else:
    print("\n✅ PASS: 全流程正常")

# 保存完整追踪
with open("/tmp/fs_trace.json", "w") as f:
    json.dump({
        "start": start_result,
        "submit1": sub_result,
        "refresh": ref_result,
        "submit2": sub_result2,
    }, f, indent=2, ensure_ascii=False)
print("\n完整追踪: /tmp/fs_trace.json")