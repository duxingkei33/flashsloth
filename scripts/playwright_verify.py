#!/usr/bin/env python3
"""
Playwright 独立验证脚本 — 在子进程中运行，避免 WSGI 线程问题。
被 routes/accounts.py 中的 _do_playwright_verify() 调用。

用法: python3 playwright_verify.py <account_id>
输出: JSON 到 stdout
"""
import sys, os, json, re, time

# 添加项目路径
sys.path.insert(0, os.path.expanduser("~/.hermes"))
sys.path.insert(0, os.path.expanduser("~/.hermes/flashsloth"))

from playwright.sync_api import sync_playwright
from flashsloth.core.database import get_db
from flashsloth.core.credential_crypto import decrypt_config
import sqlite3 as s3


def verify_account(aid: int) -> dict:
    """使用 Playwright 验证账号登录状态"""
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
        "has_cookie": False,
        "has_site_url": False,
        "site_url": "",
        "error": "",
    }

    try:
        conn = get_db()
        conn.row_factory = s3.Row
        row = conn.execute(
            "SELECT * FROM platform_accounts WHERE id=?", (aid,)
        ).fetchone()
        conn.close()

        if not row:
            result["error"] = "账号不存在"
            return result

        acct = dict(row)
        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        decrypt_config(cfg)

        cookie = cfg.get("cookie", "")
        site_url = cfg.get("site_url", "")
        platform_username = cfg.get("username", "")

        result["account_name"] = acct.get("account_name", "")
        result["platform"] = acct.get("platform", "")
        result["is_active"] = bool(acct["is_active"])
        result["has_cookie"] = bool(cookie)
        result["has_site_url"] = bool(site_url)
        result["site_url"] = site_url or ""

        static_platforms = {"github_pages_blog", "github_pages", "static_site"}
        is_static = acct.get("platform", "") in static_platforms

        # ── 静态站点 ──
        if is_static and site_url:
            import requests as _req
            try:
                r = _req.get(
                    site_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    timeout=15,
                    allow_redirects=True,
                )
                result["page_title"] = re.search(r"<title>(.*?)</title>", r.text).group(1) if re.search(r"<title>(.*?)</title>", r.text) else "(无标题)"
                if r.status_code == 200:
                    result["status"] = "✅ 站点可浏览"
                else:
                    result["status"] = f"⚠️ 站点返回 HTTP {r.status_code}"
            except Exception as e:
                result["status"] = f"❌ 站点不可达: {str(e)[:100]}"
            return result

        if not site_url:
            result["status"] = "🔗 未配置站点 URL"
            return result

        # ── Playwright 验证 ──
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

            # 检查是否被重定向到登录页
            login_keywords = ["login", "signin", "passport", "oauth", "logon", "logging",
                              "member.php", "logging.php", "connect.php", "login.php"]
            redirected_to_login = any(kw in page_url_lower for kw in login_keywords)

            # 查找登录指示器
            indicators = []
            username_found_in_body = False

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
            if re.search(r"我的中心", body_text):
                indicators.append("我的中心")

            if platform_username and len(platform_username) >= 2:
                escaped = re.escape(platform_username)
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
                        indicators.append(f"欢迎/用户信息")
                        break

            # ── 提取用户名、积分、等级（深度验证） ──
            extracted_username = ""

            # 优先使用 config 中的 username（只要在页面中出现）
            # 避免被 "欢迎 新会员" 等模糊模式误匹配
            if platform_username and re.search(re.escape(platform_username), body_text):
                extracted_username = platform_username

            # 从页面文本提取用户名（仅当 config 用户名未提取到时）
            if not extracted_username:
                username_patterns = [
                    r'欢迎您回来[：:]\s*([\u4e00-\u9fff\w]+)',
                    r'<title>[^<]*?([\u4e00-\u9fff\w]+)[^<]*?的个人资料',
                    r'"nickname"\s*[:=]\s*"([^"]+)"',
                    r'"username"\s*[:=]\s*"([^"]+)"',
                    r'"display_name"\s*[:=]\s*"([^"]+)"',
                ]
                for pat in username_patterns:
                    m = re.search(pat, body_text)
                    if m and m.group(1) and len(m.group(1).strip()) >= 2:
                        extracted_username = m.group(1).strip()
                        break

            # 提取积分
            extracted_points = 0
            points_label = "积分"
            point_patterns = [
                r'积分[：:>\s]*(\d[\d,.]*)',
                r'积分.*?(\d[\d,.]*)',
                r'(经验|积分|等级|粉丝)[：:>\s]*(\d[\d,.]*)',
                r'class="[^"]*credit[^"]*"[^>]*>(\d[\d,.]*)',
                r'points[\">\s]*(\d+)',
            ]
            for pat in point_patterns:
                m = re.search(pat, body_text)
                if m:
                    try:
                        val = m.group(2).replace(",", "").replace(".", "") if m.lastindex and m.lastindex >= 2 else m.group(1).replace(",", "").replace(".", "")
                        extracted_points = int(val)
                    except (ValueError, IndexError):
                        pass
                    break

            # 提取等级
            extracted_level = ""
            level_patterns = [
                r'用户组[：:>\s]+([^<]{2,20})',
                r'等级[：:>\s]+([^<]{2,20})',
                r'(Lv\.?\s*\d+|V\d+)',
            ]
            for pat in level_patterns:
                m = re.search(pat, body_text, re.IGNORECASE)
                if m:
                    level_val = m.group(1).strip().split('\n')[0].strip()
                    if level_val and len(level_val) >= 2:
                        extracted_level = level_val
                        break

            # 判断登录状态
            has_exit_or_logout = any(kw in str(indicators) for kw in ["退出", "注销"])
            is_logged_in = (
                not redirected_to_login
                and has_exit_or_logout  # 必须！页面中有"退出"或"注销"才是强登录证据
                and (
                    len(indicators) >= 2          # 至少有2个指示器
                    or username_found_in_body      # 或者配置的用户名在页面中找到
                )
            )

            result["logged_in"] = is_logged_in
            result["username_indicators"] = indicators[:5]
            result["username"] = extracted_username
            result["display_name"] = extracted_username
            result["points"] = extracted_points
            result["points_label"] = points_label
            result["level"] = extracted_level

            # Status 消息 —— 包含用户名/积分/等级
            if is_logged_in:
                parts = []
                # 安全兜底：如果提取到的 username 与 config 不同但 config 用户名在页面中出现，优先使用 config 用户名
                status_username = extracted_username
                if platform_username and extracted_username != platform_username:
                    if re.search(re.escape(platform_username), body_text):
                        status_username = platform_username
                if status_username:
                    parts.append(status_username)
                if extracted_points:
                    parts.append(f"{points_label}:{extracted_points}")
                if extracted_level:
                    parts.append(extracted_level)
                if parts:
                    result["status"] = f"✅ {' | '.join(parts)}"
                else:
                    result["status"] = "✅ 已登录（Cookie 有效）"
            else:
                reasons = []
                if redirected_to_login:
                    reasons.append("重定向到登录页")
                if not has_exit_or_logout:
                    if len(indicators) >= 2:
                        result["status"] = "❌ Cookie 已失效（页面导航栏检测到通用链接，但未检测到退出/注销按钮 — 未登录）"
                        browser.close()
                        return result
                    else:
                        reasons.append("未检测到退出/注销按钮")
                if len(indicators) < 2:
                    reasons.append(f"登录指示器不足(找到{len(indicators)}个，需要≥2)")
                if not reasons:
                    reasons.append("未检测到任何登录信息")
                reason = "；".join(reasons)
                if cookie:
                    result["status"] = f"❌ Cookie 已失效（{reason}）"
                else:
                    result["status"] = f"❌ 未登录（无 Cookie，{reason}）"

            # 页面预览
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

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: playwright_verify.py <account_id>"}))
        sys.exit(1)

    aid = int(sys.argv[1])
    result = verify_account(aid)
    print(json.dumps(result, ensure_ascii=False, default=str))
