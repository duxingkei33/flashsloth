#!/usr/bin/env python3
"""
Playwright 独立验证脚本（原始参数模式）— 在子进程中运行，避免 WSGI 线程问题。
被 routes/accounts.py 中的 api_test_connection() 调用，在账号保存前验证凭证有效性。

用法: echo '{"cookie":"...","site_url":"...","username":"...","platform":"..."}' | python3 playwright_verify_raw.py
输入: JSON 到 stdin
输出: JSON 到 stdout

⚠️ 铁律：必须找到真实的用户登录指示器才返回 logged_in=True。
   必须检测到「退出」或「注销」作为强登录证据，且至少 2 个独立登录指示器。
"""

import sys, os, json, re, time

sys.path.insert(0, os.path.expanduser("~/.hermes"))
sys.path.insert(0, os.path.expanduser("~/.hermes/flashsloth"))

from playwright.sync_api import sync_playwright


def verify_raw(cookie: str, site_url: str, platform_username: str = "",
               platform: str = "", cookies_json: str = "",
               storage: dict | None = None) -> dict:
    """使用 Playwright 验证原始凭证的登录状态"""
    result = {
        "success": True,
        "logged_in": None,
        "status": "",
        "username_indicators": [],
        "username": "",
        "display_name": "",
        "points": 0,
        "level": "",
        "page_title": "",
        "page_url": "",
        "page_preview": "",
        "has_cookie": bool(cookie),
        "has_site_url": bool(site_url),
        "site_url": site_url or "",
        "platform": platform,
        "error": "",
    }

    # ── 空值检查 ──
    if not site_url:
        result["status"] = "🔗 未配置站点 URL"
        return result
    if not cookie:
        result["status"] = "❌ 无 Cookie"
        return result

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu", "--disable-dev-shm-usage",
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--ignore-certificate-errors",
                ],
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="zh-CN",
            )

            # ── 注入 Cookie（优先使用结构化 cookies_json 保留 domain，铁律#19）──
            if cookies_json:
                try:
                    cookies_list = json.loads(cookies_json)
                    ctx.add_cookies(cookies_list)
                except (json.JSONDecodeError, Exception):
                    # 降级到扁平字符串
                    pass
            elif cookie:
                domain = site_url.replace("https://", "").replace("http://", "").split("/")[0]
                cookies = []
                for pair in cookie.split(";"):
                    pair = pair.strip()
                    if not pair or "=" not in pair:
                        continue
                    n, v = pair.split("=", 1)
                    cookies.append({"name": n.strip(), "value": v.strip(),
                                    "domain": f".{domain}", "path": "/"})
                ctx.add_cookies(cookies)

            # ── 注入 localStorage/sessionStorage（预留）──
            if storage:
                try:
                    page_for_storage = ctx.new_page()
                    page_for_storage.goto(site_url, wait_until="domcontentloaded", timeout=15000)
                    for item in storage.get("localStorage", []):
                        page_for_storage.evaluate(f"localStorage.setItem('{item['key']}', '{item['value']}')")
                    for item in storage.get("sessionStorage", []):
                        page_for_storage.evaluate(f"sessionStorage.setItem('{item['key']}', '{item['value']}')")
                    page_for_storage.close()
                except Exception:
                    pass

            page = ctx.new_page()
            page.goto(site_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

            result["page_title"] = page.title()
            body_text = page.inner_text("body")[:2000]
            page_url_lower = page.url.lower()
            result["page_url"] = page.url

            # ── 检查是否被重定向到登录页 ──
            login_keywords = ["login", "signin", "passport", "oauth", "logon",
                              "logging", "member.php", "logging.php",
                              "connect.php", "login.php"]
            redirected_to_login = any(kw in page_url_lower for kw in login_keywords)

            # ── 查找登录指示器 ──
            indicators = []
            username_found_in_body = False

            # 强证据：退出/注销
            if re.search(r"退出", body_text):
                indicators.append("退出")
            if re.search(r"注销", body_text):
                indicators.append("注销")
            # 弱证据：个人中心等
            if re.search(r"个人中心", body_text):
                indicators.append("个人中心")
            if re.search(r"我的帖子", body_text):
                indicators.append("我的帖子")
            if re.search(r"我的文章", body_text):
                indicators.append("我的文章")
            if re.search(r"我的中心", body_text):
                indicators.append("我的中心")
            if re.search(r"个人主页", body_text):
                indicators.append("个人主页")

            # 用户名匹配
            if platform_username and len(platform_username.strip()) >= 2:
                escaped = re.escape(platform_username.strip())
                if re.search(escaped, body_text):
                    username_found_in_body = True
                    indicators.append(f"用户名:{platform_username}")
                # 欢迎信息
                for pat in [
                    rf"欢迎[：: 　]*{escaped}",
                    rf"{escaped}[，,。.]*欢迎",
                    rf"你好[：: 　]*{escaped}",
                    rf"个人资料.*{escaped}",
                    rf"{escaped}.*个人资料",
                ]:
                    if re.search(pat, body_text, re.IGNORECASE):
                        indicators.append("欢迎/用户信息")
                        break

            # ── 提取用户名 ──
            extracted_username = ""

            # 优先级1: 如果传入的用户名出现在页面中，优先用它
            if platform_username and len(platform_username.strip()) >= 2:
                escaped = re.escape(platform_username.strip())
                if re.search(escaped, body_text):
                    extracted_username = platform_username.strip()

            # 优先级2: 通过正则模式提取（不包含「欢迎 新会员」等误导模式）
            if not extracted_username:
                username_patterns = [
                    r'欢迎您回来[：:]\s*([一-鿿\w]+)',
                    r'<title>[^<]*?([一-鿿\w]+)[^<]*?的个人资料',
                    r'"nickname"\s*[:=]\s*"([^"]+)"',
                    r'"username"\s*[:=]\s*"([^"]+)"',
                    r'"display_name"\s*[:=]\s*"([^"]+)"',
                    r'"nick"\s*:\s*"([^"]+)"',
                    r'"nickName"\s*:\s*"([^"]+)"',
                    r'"userName"\s*:\s*"([^"]+)"',
                ]
                for pat in username_patterns:
                    m = re.search(pat, body_text)
                    if m and m.group(1) and len(m.group(1).strip()) >= 2:
                        extracted_username = m.group(1).strip()
                        break

            # ── 判断登录态 ──
            has_strong_exit = any(kw in str(indicators) for kw in ["退出", "注销"])

            # ⚠️ 铁律：必须同时满足以下条件才判定为已登录：
            # 1. 未被重定向到登录页
            # 2. 必须有"退出"或"注销"（强登录证据）
            # 3. 有足够的指示器（≥2 个）或配置的用户名出现在页面中
            is_logged_in = (
                not redirected_to_login
                and has_strong_exit
                and (
                    len(indicators) >= 2
                    or username_found_in_body
                )
            )

            result["logged_in"] = is_logged_in
            result["username_indicators"] = indicators[:5]
            result["username"] = extracted_username
            result["display_name"] = extracted_username

            # ── 状态消息 ──
            if is_logged_in:
                parts = []
                if extracted_username:
                    parts.append(extracted_username)
                if parts:
                    result["status"] = f"✅ {' | '.join(parts)}"
                else:
                    result["status"] = "✅ 已登录（Cookie 有效）"
            else:
                reasons = []
                if redirected_to_login:
                    reasons.append("重定向到登录页")
                if not has_strong_exit:
                    reasons.append("未检测到退出/注销按钮")
                if len(indicators) < 2:
                    reasons.append(f"登录指示器不足(找到{len(indicators)}个，需要≥2)")
                if not reasons:
                    reasons.append("未检测到任何登录信息")
                reason = "；".join(reasons)
                result["status"] = f"❌ Cookie 已失效（{reason}）"

            # ── 页面预览 ──
            if indicators:
                snippets = []
                for ind in indicators[:3]:
                    idx = body_text.find(ind)
                    if idx >= 0:
                        start = max(0, idx - 100)
                        end = min(len(body_text), idx + len(ind) + 100)
                        snippets.append(body_text[start:end].strip())
                result["page_preview"] = "\n".join(snippets)[:600]
            else:
                result["page_preview"] = body_text[:600]

            browser.close()

    except Exception as e:
        result["success"] = False
        result["logged_in"] = False
        result["status"] = f"❌ Playwright 异常: {str(e)[:120]}"
        result["error"] = str(e)[:200]

    return result


if __name__ == "__main__":
    try:
        input_data = json.loads(sys.stdin.read())
        cookie = input_data.get("cookie", "")
        site_url = input_data.get("site_url", "")
        username = input_data.get("username", "")
        platform = input_data.get("platform", "")
        cookies_json = input_data.get("cookies_json", "")
        storage = input_data.get("storage")
    except (json.JSONDecodeError, Exception):
        print(json.dumps({"success": False, "error": "Invalid input JSON",
                          "logged_in": False, "status": "❌ 输入参数解析失败"}))
        sys.exit(0)

    result = verify_raw(cookie, site_url, username, platform,
                        cookies_json=cookies_json, storage=storage)
    print(json.dumps(result, ensure_ascii=False, default=str))
