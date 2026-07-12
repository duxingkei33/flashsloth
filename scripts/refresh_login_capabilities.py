"""
每15分钟执行的 P0 登录能力探索脚本。
重新探索过时(>12h)平台的登录能力，更新 JSON 文件。

兼容 cron 环境：Playwright headless，无显示依赖。
"""
import json
import os
import re
import sys
import base64
from datetime import datetime, timezone

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_reports")
STALE_THRESHOLD_HOURS = 12

# 平台 → 登录页 URL 映射
LOGIN_URLS = {
    "csdn": "https://passport.csdn.net/login",
    "zhihu": "https://www.zhihu.com/signin",
    "bilibili": "https://www.bilibili.com/",
    "juejin": "https://juejin.cn/",
    "wechat_mp": "https://mp.weixin.qq.com/",
    "wechat": "https://mp.weixin.qq.com/",
    "oshwhub": "https://passport.jlc.com/login",
    "xianyu": "https://www.goofish.com/",
    "xianyu_v2": "https://www.goofish.com/",
    "xianyu_auto_reply": "https://www.goofish.com/",
    "xianyu_products": "https://www.goofish.com/",
    "xianyu_sidecar": "https://www.goofish.com/",
    "discuz": None,  # 通用 Discuz，需要具体 site_url
    "amobbs": None,
    "mydigit": None,
    "wordpress": None,  # 需要用户 site_url
    "rss": None,  # 无登录页
    "twitter": None,  # OAuth1，需要 API 凭证
}

# 平台名 → JSON 文件名映射
PLATFORM_CAP_MAP = {
    "wechat": "wechat_mp",
    "xianyu_v2": "xianyu",
    "xianyu_sidecar": "xianyu",
    "xianyu_auto_reply": "xianyu",
    "xianyu_products": "xianyu",
}


def is_stale(platform: str) -> bool:
    """检查 JSON 是否过时"""
    json_name = PLATFORM_CAP_MAP.get(platform, platform)
    path = os.path.join(REPORTS_DIR, f"{json_name}_login_capabilities.json")
    if not os.path.exists(path):
        return True  # 不存在就是需要探索
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        explored_at = data.get("explored_at", "")
        if not explored_at:
            return True
        # 解析时间
        explored_at = explored_at.replace("Z", "+00:00")
        explored_dt = datetime.fromisoformat(explored_at)
        now = datetime.now(timezone.utc)
        age_hours = (now - explored_dt).total_seconds() / 3600
        return age_hours > STALE_THRESHOLD_HOURS
    except Exception:
        return True


def explore_platform(platform: str) -> dict:
    """用 Playwright 探索平台的登录能力"""
    json_name = PLATFORM_CAP_MAP.get(platform, platform)
    url = LOGIN_URLS.get(platform) or LOGIN_URLS.get(json_name)
    if not url:
        return {"platform": platform, "error": "无登录页 URL"}

    try:
        # 延迟导入
        from flashsloth.core.browser_engine import BrowserEngine

        engine = BrowserEngine.get_instance()
        engine.start()
        ctx = engine.create_isolated_context()
        if not ctx:
            ctx = engine.create_isolated_context()
        page = ctx.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # 尝试点击可能的登录方式切换 tab — 某些平台默认隐藏密码登录
        _tab_clicked = False
        for tab_text in ["账号登录", "账号", "密码登录", "账户密码", "手机号登录"]:
            try:
                tab_btn = page.query_selector(
                    f"button:has-text('{tab_text}'), "
                    f"a:has-text('{tab_text}'), "
                    f"span:has-text('{tab_text}'), "
                    f"li:has-text('{tab_text}'), "
                    f"[class*='tab']:has-text('{tab_text}')"
                )
                if tab_btn:
                    tab_btn.click()
                    page.wait_for_timeout(1500)
                    _tab_clicked = True
                    break
            except Exception:
                pass

        # 截图
        screenshot_dir = os.path.join(REPORTS_DIR, "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, f"{json_name}_login.png")
        try:
            page.screenshot(path=screenshot_path, full_page=False)
        except Exception:
            screenshot_path = ""

        # 检测
        body_text = page.inner_text("body")[:3000]
        page_html = page.content()
        page_url = page.url
        page_title = page.title()

        has_password = page.query_selector("input[type='password']") is not None
        has_phone = bool(re.search(r"手机号|电话号码|phone|mobile", body_text, re.I))
        has_code_btn = bool(re.search(r"获取验证码|发送验证码|get.*code|send.*code", body_text, re.I))
        has_qrcode = page.query_selector(
            "img[src*='qrcode'], canvas[class*='qrcode'], div[class*='qrcode']"
        ) is not None
        has_wechat = bool(re.search(r"微信|wechat|weixin", body_text, re.I)) or page.query_selector(
            "img[alt*='wechat'], i[class*='wechat']"
        ) is not None
        has_app_qr = bool(re.search(r"APP扫码|APP.*扫码|客户端扫码", body_text, re.I))
        has_oauth = page.query_selector(
            "[class*='oauth'], [class*='third'], [class*='social'], "
            "a[href*='qq'], a[href*='weibo'], a[href*='github']"
        ) is not None

        # 第三方登录
        third_providers = []
        for prov, patterns in [
            ("qq", r"qq\\.com|QQ"),
            ("weibo", r"weibo\\.com|微博"),
            ("github", r"github\\.com|GitHub"),
            ("google", r"google|Google"),
            ("wechat_oauth", r"微信登录|wechat"),
        ]:
            if re.search(patterns, page_html, re.I):
                third_providers.append(prov)
        third_providers = list(dict.fromkeys(third_providers))

        methods = []
        if has_password:
            methods.append({
                "method": "password", "label": "账号密码登录",
                "detected": True, "selector": "input[type='password']"
            })
        phone_detected = has_phone and has_code_btn
        if phone_detected:
            methods.append({
                "method": "phone", "label": "手机验证码登录",
                "detected": True, "selector": "input[type='tel']"
            })
        qrcode_sub_types = []
        if has_wechat:
            qrcode_sub_types.append({"id": "wechat", "label": "微信扫码", "detected": True})
        if has_app_qr:
            qrcode_sub_types.append({"id": "app", "label": "APP扫码", "detected": True})
        if has_qrcode or qrcode_sub_types:
            qrcode_sub_types = qrcode_sub_types or [{"id": "default", "label": "二维码登录", "detected": True}]
            methods.append({
                "method": "qrcode", "label": "扫码登录",
                "detected": True, "sub_types": qrcode_sub_types,
                "selector": "img[src*='qrcode']"
            })
        if third_providers or has_oauth:
            methods.append({
                "method": "oauth", "label": "第三方账号登录",
                "detected": True, "providers": third_providers or ["wechat_oauth", "qq", "weibo"]
            })
        methods.append({"method": "cookie", "label": "Cookie粘贴", "detected": True})

        detected_labels = [m["label"] for m in methods if m.get("detected") and m["method"] != "cookie"]
        note_parts = [f"{json_name}登录页支持"]
        note_parts.append("/".join(detected_labels))
        if third_providers:
            note_parts.append(f"/第三方({','.join(third_providers)})")
        note = "".join(note_parts)

        cap_data = {
            "platform": json_name,
            "explored_at": datetime.now(timezone.utc).isoformat(),
            "login_url": url,
            "login_methods": methods,
            "note": note,
            "raw_detection": {
                "has_password_input": has_password,
                "has_phone_input": has_phone,
                "has_code_button": has_code_btn,
                "has_qrcode_img": has_qrcode,
                "has_wechat": has_wechat,
                "has_app_qr": has_app_qr,
                "third_party_providers": third_providers,
                "page_title": page_title,
                "page_url": page_url,
            },
            "error": None,
            "screenshot": screenshot_path,
        }

        # 保存 JSON
        report_path = os.path.join(REPORTS_DIR, f"{json_name}_login_capabilities.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(cap_data, f, ensure_ascii=False, indent=2)

        page.close()
        ctx.close()

        return {
            "platform": platform,
            "success": True,
            "methods": [m["method"] for m in methods if m.get("detected")],
            "note": note,
        }

    except Exception as e:
        # 清理
        try:
            if 'page' in dir():
                page.close()
            if 'ctx' in dir():
                ctx.close()
        except Exception:
            pass
        return {"platform": platform, "success": False, "error": str(e)[:200]}


def update_summary():
    """更新 _login_capabilities_summary.json"""
    summary = {}
    for fp in os.listdir(REPORTS_DIR):
        if not fp.endswith("_login_capabilities.json") or fp.startswith("_"):
            continue
        try:
            with open(os.path.join(REPORTS_DIR, fp), "r", encoding="utf-8") as f:
                data = json.load(f)
            platform = data.get("platform", fp.replace("_login_capabilities.json", ""))
            methods = [m["method"] for m in data.get("login_methods", []) if m.get("detected")]
            summary[platform] = {
                "login_methods": methods,
                "detail": "BASIC",
                "error": data.get("error"),
                "explored_at": data.get("explored_at", ""),
            }
        except Exception:
            pass

    summary_path = os.path.join(REPORTS_DIR, "_login_capabilities_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)

    return summary


if __name__ == "__main__":
    print(f"=== P0 登录能力 Cron 探索 ===")
    print(f"时间: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    print()

    # 检查哪些平台过时
    stale_platforms = [p for p in LOGIN_URLS if is_stale(p) and LOGIN_URLS.get(p)]
    fresh_platforms = [p for p in LOGIN_URLS if not is_stale(p)]
    skipped = [p for p in LOGIN_URLS if not LOGIN_URLS.get(p)]

    print(f"已探索(新鲜): {len(fresh_platforms)}")
    print(f"待探索(过时): {len(stale_platforms)}")
    print(f"跳过: {len(skipped)} ({', '.join(skipped) if skipped else '无'})")
    print()

    # 分批探索（每批最多2个，避免浏览器冲突）
    BATCH_SIZE = 2
    results = []
    for i in range(0, len(stale_platforms), BATCH_SIZE):
        batch = stale_platforms[i:i+BATCH_SIZE]
        print(f"--- 探索批次 {i//BATCH_SIZE + 1}: {', '.join(batch)} ---")
        for plat in batch:
            print(f"  探索 {plat}...", end=" ", flush=True)
            result = explore_platform(plat)
            results.append(result)
            if result.get("success"):
                print(f"✅ 方法: {', '.join(result.get('methods', []))}"[:80])
            else:
                print(f"❌ {result.get('error', '未知错误')}"[:60])

    # 更新摘要
    update_summary()
    print()
    print(f"=== 结果 ===")
    print(f"成功: {sum(1 for r in results if r.get('success'))}")
    print(f"失败: {sum(1 for r in results if not r.get('success'))}")
    print(f"新探索/已更新平台: {len(results)}")

    if results:
        print()
        print("详细结果:")
        for r in results:
            if r.get("success"):
                print(f"  ✅ {r['platform']:20s} → 方法: {', '.join(r.get('methods', []))}")
            else:
                print(f"  ❌ {r['platform']:20s} → {r.get('error', '?')}")
