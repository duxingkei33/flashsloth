#!/usr/bin/env python3
"""
Playwright 独立验证脚本（原始参数模式）— 用于添加账号前的连接测试。
被 routes/accounts.py 中的 api_test_connection() 调用。

输入: stdin JSON
  {"cookie": "...", "site_url": "...", "username": "duxingkei", "platform": "discuz"}
输出: stdout JSON
"""
import sys, os, json, re, time

sys.path.insert(0, os.path.expanduser("~/.hermes"))
sys.path.insert(0, os.path.expanduser("~/.hermes/flashsloth"))

from playwright.sync_api import sync_playwright


def verify_raw(params: dict) -> dict:
    cookie = params.get("cookie", "")
    site_url = params.get("site_url", "")
    platform_username = params.get("username", "")
    platform = params.get("platform", "")

    result = {
        "success": True,
        "logged_in": None,
        "username": "",
        "display_name": "",
        "points": 0,
        "level": "",
        "status": "",
        "username_indicators": [],
        "page_title": "",
        "page_url": "",
        "page_preview": "",
        "has_cookie": bool(cookie),
        "has_site_url": bool(site_url),
        "site_url": site_url or "",
        "platform": platform,
        "error": "",
    }

    if not site_url:
        result["status"] = "🔗 未配置站点 URL"
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu", "--disable-dev-shm-usage",
                    "--no-sandbox", "--disable-setuid-sandbox",
                ],
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )

            if cookie:
                domain = site_url.replace("https://", "").replace("http://", "").split("/")[0]
                cookies = []
                for pair in cookie.split(";"):
                    pair = pair.strip()
                    if not pair or "=" not in pair:
                        continue
                    n, v = pair.split("=", 1)
                    cookies.append({"name": n.strip(), "value": v.strip(), "domain": f".{domain}", "path": "/"})
                ctx.add_cookies(cookies)

            page = ctx.new_page()
            page.goto(site_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            result["page_title"] = page.title()
            body_text = page.inner_text("body")[:2000]
            page_url_lower = page.url.lower()
            result["page_url"] = page.url

            # ── 登录指示器检测 ──
            login_keywords = ["login", "signin", "passport", "oauth", "logon",
                              "member.php", "logging.php", "connect.php"]
            redirected_to_login = any(kw in page_url_lower for kw in login_keywords)

            indicators = []
            if re.search(r"退出", body_text):
                indicators.append("退出")
            if re.search(r"注销", body_text):
                indicators.append("注销")
            if re.search(r"个人中心", body_text):
                indicators.append("个人中心")
            if re.search(r"我的帖子", body_text):
                indicators.append("我的帖子")
            if re.search(r"我的文章", body_text):
                indicators.append("我的文章")

            username_in_body = False
            if platform_username and len(platform_username) >= 2:
                escaped = re.escape(platform_username)
                if re.search(escaped, body_text):
                    username_in_body = True
                    indicators.append(f"用户名:{platform_username}")

            # ── 严格判断登录态 ──
            has_strong_exit = bool(re.search(r"退出|注销", body_text))
            sufficient_indicators = len(indicators) >= 2

            if not redirected_to_login and has_strong_exit and (sufficient_indicators or username_in_body):
                result["logged_in"] = True
                result["username_indicators"] = indicators[:5]
                result["username"] = platform_username
                result["display_name"] = platform_username

                # 提取积分/等级
                extracted_points = 0
                for pat in [r"积分[：:>\s]*(\d[\d,.]*)", r"points[\">\s]*(\d+)"]:
                    m = re.search(pat, body_text)
                    if m:
                        try:
                            extracted_points = int(m.group(1).replace(",", "").replace(".", ""))
                        except ValueError:
                            pass
                        break
                result["points"] = extracted_points

                extracted_level = ""
                for pat in [r"用户组[：:>\s]+([^<]{2,20})", r"等级[：:>\s]+([^<]{2,20})", r"(Lv\.?\s*\d+|V\d+)"]:
                    m = re.search(pat, body_text, re.IGNORECASE)
                    if m:
                        extracted_level = m.group(1).strip()
                        if extracted_level and len(extracted_level) >= 2:
                            break
                result["level"] = extracted_level

                parts = [platform_username] if platform_username else []
                if extracted_points:
                    parts.append(f"积分:{extracted_points}")
                if extracted_level:
                    parts.append(extracted_level)
                result["status"] = f"✅ {' | '.join(parts)}" if parts else "✅ Cookie有效"
            elif redirected_to_login:
                result["logged_in"] = False
                result["status"] = "❌ Cookie已失效（重定向到登录页）"
            elif not has_strong_exit:
                result["logged_in"] = False
                if indicators:
                    result["status"] = f"❌ Cookie已失效（检测到{len(indicators)}个页面元素但无退出/注销按钮）"
                else:
                    result["status"] = "❌ Cookie已失效（未检测到登录信息）"
            else:
                result["logged_in"] = False
                result["status"] = "❌ Cookie已失效（未检测到完整登录态）"

            result["page_preview"] = body_text[:500]
            browser.close()

    except Exception as e:
        result["success"] = False
        result["logged_in"] = False
        result["status"] = f"❌ Playwright异常: {str(e)[:120]}"
        result["error"] = str(e)[:200]

    return result


if __name__ == "__main__":
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"success": False, "error": "No input data"}))
        sys.exit(1)
    try:
        params = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"success": False, "error": "Invalid JSON input"}))
        sys.exit(1)
    result = verify_raw(params)
    print(json.dumps(result, ensure_ascii=False, default=str))
