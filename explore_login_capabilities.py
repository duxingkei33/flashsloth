"""P0: 探索平台登录能力 — Playwright 真实检测"""
import json, os, base64, time, sys
from datetime import datetime, timezone

PLATFORMS = [
    ("csdn",      "https://passport.csdn.net/login"),
    ("zhihu",     "https://www.zhihu.com/signin"),
    ("bilibili",  "https://www.bilibili.com/"),
    ("juejin",    "https://juejin.cn/"),
    ("wechat_mp", "https://mp.weixin.qq.com/"),
    ("oshwhub",   "https://passport.jlc.com/login"),
    ("xianyu",    "https://www.goofish.com/"),
]

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "platform_reports")

def detect_login_methods(page):
    """分析页面，检测支持的登录方式，返回 list[dict]"""
    methods = []
    html_lower = page.content().lower()
    page_text = page.inner_text("body")[:3000]
    text_lower = page_text.lower()
    visible = page.evaluate("""() => {
        const els = document.querySelectorAll('input, button, a, img, [class*=login], [class*=tab], [class*=qrcode], [class*=wechat], [class*=phone], [class*=oauth], [class*=third]');
        return Array.from(els).slice(0, 200).map(e => ({
            tag: e.tagName,
            type: e.type || '',
            id: e.id,
            cls: e.className,
            text: (e.textContent || '').trim().slice(0, 60),
            placeholder: e.placeholder || '',
            alt: e.alt || '',
            src: (e.src || '').slice(0, 100),
            href: (e.href || '').slice(0, 100),
        }));
    }""")

    # 1. 检测密码登录: <input type="password">
    has_password_input = page.query_selector('input[type="password"]') is not None
    # 也可能是 type="text" 但有 password 相关 id/name
    password_fields = page.query_selector_all(
        'input[type="password"], input[name*="pass"], input[id*="pass"], '
        'input[placeholder*="密码"], input[placeholder*="pass"]'
    )
    has_password = has_password_input or len(password_fields) > 0
    
    # 2. 检测手机验证码登录
    has_phone_input = False
    phone_inputs = page.query_selector_all(
        'input[type="tel"], input[name*="phone"], input[id*="phone"], '
        'input[placeholder*="手机"], input[placeholder*="phone"], '
        'input[name*="mobile"], input[id*="mobile"]'
    )
    has_code_btn = False
    code_btns = page.query_selector_all(
        'button:has-text("验证码"), button:has-text("发送"), '
        'button:has-text("获取"), button:has-text("code"), '
        '[class*="code"] button, [class*="sms"] button, '
        'a:has-text("获取"), a:has-text("验证码")'
    )
    if len(phone_inputs) > 0:
        has_phone_input = True
    if len(code_btns) > 0:
        has_code_btn = True
    # 文字检测
    has_phone_text = any(kw in text_lower for kw in [
        "手机号", "手机号码", "短信登录", "短信验证码", "验证码登录",
        "手机验证", "手机登录", "phone", "mobile", "短信"
    ])
    has_phone = has_phone_input or (has_phone_text and has_code_btn)

    # 3. 检测二维码/扫码登录
    qrcode_subtypes = []
    # 查找二维码图片
    qr_images = page.query_selector_all(
        'img[src*="qrcode"], img[src*="qr"], img[class*="qrcode"], '
        'img[id*="qrcode"], img[alt*="二维码"], img[alt*="qrcode"], '
        'img[alt*="扫码"], img[alt*="scan"]'
    )
    has_qrcode_img = len(qr_images) > 0

    # 检测微信相关
    wechat_els = page.query_selector_all(
        '[class*="wechat"], [id*="wechat"], img[alt*="微信"], '
        'img[src*="wechat"], *:has-text("微信"), *:has-text("WeChat")'
    )
    has_wechat = len(wechat_els) > 0

    # 检测 APP 扫码
    app_qr_els = page.query_selector_all(
        '*:has-text("APP"), *:has-text("app"), *:has-text("客户端"), '
        '*:has-text("扫码"), [class*="app-qr"], [class*="appqr"]'
    )
    has_app_qr = len(app_qr_els) > 0

    # 检测第三方登录图标
    third_party_login = False
    third_party_providers = []
    # 常见第三方登录
    for provider, keywords in [
        ("qq", ["qq", "QQ", "腾讯QQ"]),
        ("weibo", ["微博", "weibo", "Weibo"]),
        ("github", ["github", "GitHub", "Github"]),
        ("google", ["google", "Google"]),
        ("wechat_oauth", ["微信登录", "wechat"]),
        ("alipay", ["支付宝", "alipay"]),
        ("taobao", ["淘宝", "taobao"]),
    ]:
        for kw in keywords:
            if kw in html_lower:
                els = page.query_selector_all(
                    f'img[alt*="{kw}"], img[title*="{kw}"], '
                    f'[class*="{kw.lower()}"], [id*="{kw.lower()}"], '
                    f'a[href*="{kw.lower()}"]'
                )
                if len(els) > 0 or kw in text_lower:
                    third_party_login = True
                    third_party_providers.append(provider)
                    break

    # 子类型：二维码扫码
    qrcode_sub_types = []
    if has_wechat:
        qrcode_sub_types.append({
            "id": "wechat", "label": "微信扫码", "detected": has_wechat
        })
    if has_app_qr:
        qrcode_sub_types.append({
            "id": "app", "label": "APP扫码", "detected": has_app_qr
        })

    # 4. Cookie — 通用支持，始终为 true
    has_cookie = True

    # 构建结果
    login_methods = []

    if has_password:
        login_methods.append({
            "method": "password",
            "label": "账号密码登录",
            "detected": True,
            "selector": "input[type='password']" if has_password_input else "password-like input",
        })

    if has_phone:
        login_methods.append({
            "method": "phone",
            "label": "手机验证码登录",
            "detected": True,
            "selector": "phone input" if has_phone_input else "text match",
        })

    if has_qrcode_img or has_wechat or has_app_qr:
        qr_entry = {
            "method": "qrcode",
            "label": "扫码登录",
            "detected": True,
        }
        if qrcode_sub_types:
            qr_entry["sub_types"] = qrcode_sub_types
        if qr_images:
            qr_entry["selector"] = "img[src*='qrcode']"
        login_methods.append(qr_entry)

    if third_party_login and third_party_providers:
        login_methods.append({
            "method": "oauth",
            "label": "第三方账号登录",
            "detected": True,
            "providers": list(set(third_party_providers)),
        })

    login_methods.append({
        "method": "cookie",
        "label": "Cookie粘贴",
        "detected": True,
    })

    return login_methods, {
        "has_password_input": has_password_input,
        "has_phone_input": has_phone_input,
        "has_code_button": bool(len(code_btns) > 0),
        "has_qrcode_img": has_qrcode_img,
        "has_wechat": has_wechat,
        "has_app_qr": has_app_qr,
        "third_party_providers": third_party_providers,
        "page_title": page.title(),
        "page_url": page.url,
    }


def explore_platform(name, url):
    """用 Playwright 探索单个平台登录能力"""
    from playwright.sync_api import sync_playwright
    
    result = {
        "platform": name,
        "explored_at": datetime.now(timezone.utc).isoformat(),
        "login_url": url,
        "login_methods": [],
        "note": "",
        "raw_detection": {},
        "error": None,
    }

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )
            page = ctx.new_page()
            try:
                # 尝试访问登录页
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)  # 等待 JS 渲染
                
                # 尝试点击"登录"按钮（如果页面有登录按钮需要点击才能弹窗）
                login_btn = page.query_selector(
                    'button:has-text("登录"), a:has-text("登录"), '
                    '[class*="login"] button, [class*="login"] a, '
                    '.login-btn, #login-btn, .header-login, '
                    'button:has-text("sign in"), a:has-text("sign in")'
                )
                if login_btn:
                    try:
                        login_btn.click()
                        page.wait_for_timeout(3000)
                    except:
                        pass

                # 检测登录方式
                login_methods, raw = detect_login_methods(page)
                result["login_methods"] = login_methods
                result["raw_detection"] = raw

                # 生成摘要
                method_names = [m["label"] for m in login_methods if m.get("detected")]
                if raw.get("third_party_providers"):
                    third_str = "/".join(raw["third_party_providers"])
                    method_names.append(f"第三方({third_str})")
                result["note"] = f"{name}登录页支持{'/'.join(method_names)}"

                # 截图保存
                screenshots_dir = os.path.join(REPORTS_DIR, "screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                screenshot_path = os.path.join(screenshots_dir, f"{name}_login.png")
                page.screenshot(path=screenshot_path, full_page=True)
                result["screenshot"] = screenshot_path

            except Exception as e:
                result["error"] = str(e)[:2000]
            finally:
                page.close()
                ctx.close()
                browser.close()

    except Exception as e:
        result["error"] = f"Playwright init error: {str(e)[:500]}"

    return result


def main():
    os.makedirs(REPORTS_DIR, exist_ok=True)
    results = {}

    for name, url in PLATFORMS:
        report_path = os.path.join(REPORTS_DIR, f"{name}_login_capabilities.json")
        
        # 检查已有报告是否过期（超过24小时则重新探索）
        if os.path.exists(report_path):
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                explored = existing.get("explored_at", "")
                if explored:
                    explored_dt = datetime.fromisoformat(explored)
                    age_hours = (datetime.now(timezone.utc) - explored_dt).total_seconds() / 3600
                    if age_hours < 24 and existing.get("login_methods"):
                        print(f"⏭️ {name}: 已有报告（{age_hours:.1f}h 前），跳过")
                        results[name] = existing
                        continue
            except:
                pass

        print(f"🔍 探索 {name} ({url})...")
        result = explore_platform(name, url)
        results[name] = result

        # 写入 JSON
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        if result.get("error"):
            print(f"  ❌ 错误: {result['error']}")
        else:
            methods = [m["label"] for m in result.get("login_methods", []) if m.get("detected")]
            print(f"  ✅ 检测到登录方式: {', '.join(methods)}")
            print(f"   📝 {result.get('note', '')}")

    # 汇总报告
    print("\n" + "="*60)
    print("📊 平台登录能力探索汇总")
    print("="*60)
    for name, result in results.items():
        methods = [m["label"] for m in result.get("login_methods", []) if m.get("detected")]
        status = "❌" if result.get("error") else "✅"
        print(f"  {status} {name:15s}: {', '.join(methods)}")

    # 输出机器可读的摘要
    summary = {}
    for name, result in results.items():
        summary[name] = {
            "login_methods": [m["method"] for m in result.get("login_methods", []) if m.get("detected")],
            "error": result.get("error"),
        }
    summary_path = os.path.join(REPORTS_DIR, "_login_capabilities_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n📄 汇总写入: {summary_path}")

    return results


if __name__ == "__main__":
    main()
