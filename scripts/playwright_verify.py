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

# SSO 平台：即时密码登录插件注册表（数据驱动判断来自探索JSON）
# platform_name -> (module_path, class_name)
SSO_LOGIN_PLUGINS = {
    "oshwhub": ("plugins.oshwhub_login", "OshwhubPlaywrightLogin"),
}


def _load_platform_report(platform: str) -> dict:
    """加载平台探索报告 JSON（数据驱动，不硬编码平台名和选择器）"""
    report_path = os.path.expanduser(
        f"~/.hermes/flashsloth/platform_reports/{platform}_exploration_report.json"
    )
    if not os.path.exists(report_path):
        return {}
    try:
        with open(report_path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return {}


def _load_indicator_config(platform: str) -> dict:
    """从探索报告 JSON 加载登录指示器配置（数据驱动）"""
    report_path = os.path.expanduser(
        f"~/.hermes/flashsloth/platform_reports/{platform}_exploration_report.json"
    )
    if not os.path.exists(report_path):
        return {}
    try:
        with open(report_path, "r") as f:
            report = json.load(f)
        return report.get("login_indicator_selectors", {})
    except (json.JSONDecodeError, Exception):
        return {}


def _verify_sso_via_login(acct: dict, cfg: dict, result: dict, report: dict) -> dict:
    """对 SSO 平台做即时密码登录验证（替代 cookie 注入）

    数据驱动：从 report (探索JSON) 读取 sso_ecosystem 和 login_indicator_selectors。
    不硬编码任何平台名、选择器、URL。

    Args:
        acct: 数据库 row dict
        cfg: 解密后的 config_json dict
        result: 已有结果 dict (会被就地填充后返回)
        report: 平台探索 JSON 的完整内容

    Returns:
        填充后的 result dict
    """
    import importlib

    platform = acct.get("platform", "")
    plugin_info = SSO_LOGIN_PLUGINS.get(platform)
    if not plugin_info:
        # 没有登录插件注册 → 无法做即时登录，返回错误
        result["error"] = f"SSO 平台 {platform} 未注册登录插件，无法做即时登录验证"
        result["logged_in"] = False
        result["status"] = f"❌ SSO 验证失败：{platform} 无登录插件"
        return result

    username = cfg.get("username", "")
    password = cfg.get("password", "")
    site_url = cfg.get("site_url", "")

    if not username or not password:
        result["error"] = "SSO 平台需要用户名和密码进行即时登录，但配置中未找到"
        result["logged_in"] = False
        result["status"] = "❌ SSO 登录失败：缺少用户名或密码"
        return result

    result["has_cookie"] = False

    try:
        mod_path, cls_name = plugin_info
        mod = importlib.import_module(mod_path)
        login_cls = getattr(mod, cls_name)

        login_instance = login_cls(site_url=site_url or f"https://{platform}.com")
        try:
            login_result = login_instance.login(username=username, password=password)

            if login_result.get("logged_in"):
                # ── 登录成功 → 从探索JSON读取指示器做验证 ──
                indicator_config = report.get("login_indicator_selectors", {})
                required_keys = indicator_config.get("required_indicators_for_success", [])

                # 检查必需选择器（如 avatar CSS 选择器）
                required_ok = True
                if required_keys and login_instance.page:
                    for key in required_keys:
                        selectors = indicator_config.get(key, key)
                        if isinstance(selectors, str):
                            selectors = [selectors]
                        found = False
                        for sel in selectors:
                            try:
                                el = login_instance.page.query_selector(sel)
                                if el and el.is_visible():
                                    found = True
                                    break
                            except Exception:
                                pass
                        if not found:
                            required_ok = False

                # 获取新 cookies
                new_cookies_json = login_result.get("cookies_json", "")
                new_cookie_str = login_result.get("cookies", "")

                # 保存新 cookies 到 DB（让下次 cookie 注入也有新鲜数据）
                if new_cookies_json or new_cookie_str:
                    _update_account_cookies(acct["id"], new_cookies_json, new_cookie_str)

                # 填充结果
                result["logged_in"] = True
                result["has_cookie"] = bool(new_cookie_str)
                result["page_title"] = login_instance.page.title() if login_instance.page else ""

                # 做文本指示器检查（与已有逻辑一致）
                if login_instance.page:
                    try:
                        body_text = login_instance.page.inner_text("body")[:2000]
                        result["page_url"] = login_instance.page.url
                        indicators = []
                        if re.search(r"退出", body_text):
                            indicators.append("退出")
                        if re.search(r"注销", body_text):
                            indicators.append("注销")
                        if re.search(r"个人中心", body_text):
                            indicators.append("个人中心")
                        if username and len(username) >= 2:
                            if re.search(re.escape(username), body_text):
                                indicators.append(f"用户名:{username}")
                        result["username_indicators"] = indicators[:5]

                        # 根据 required 和 optional 指示器构造 status
                        status_parts = []
                        if required_ok and required_keys:
                            status_parts.extend(k for k in required_keys[:2])
                        for ind in indicators[:3]:
                            label = ind.replace("用户名:", "")
                            if label not in str(status_parts):
                                status_parts.append(label)
                        if status_parts:
                            result["status"] = f"✅ SSO 已登录（{' '.join(status_parts)}）"
                        else:
                            result["status"] = "✅ 已登录（SSO即时登录）"
                    except Exception:
                        result["status"] = "✅ 已登录（SSO即时登录）"
                else:
                    result["status"] = "✅ 已登录（SSO即时登录）"
            else:
                # 登录失败
                error = login_result.get("error", "未知错误")
                needs_captcha = login_result.get("needs_captcha", False)
                result["logged_in"] = False
                if needs_captcha:
                    login_url = site_url or f"https://{platform}.com"
                    result["status"] = f"🔒 SSO 需要手动验证码（登录页: {login_url}）"
                else:
                    result["status"] = f"❌ SSO 登录失败：{error[:120]}"
        finally:
            login_instance.close()
    except Exception as e:
        result["success"] = False
        result["logged_in"] = False
        result["status"] = f"❌ SSO 验证异常: {str(e)[:120]}"
        result["error"] = str(e)[:200]

    return result


def _update_account_cookies(aid: int, cookies_json: str, cookie_str: str):
    """更新账号的 cookies 到 DB（SSO即时登录后保存新凭证，铁律#19）"""
    try:
        conn = get_db()
        conn.row_factory = s3.Row
        row = conn.execute(
            "SELECT config_json FROM platform_accounts WHERE id=?", (aid,)
        ).fetchone()
        if row:
            cfg = json.loads(row[0]) if row[0] else {}
            if cookies_json:
                cfg["cookies_json"] = cookies_json
            if cookie_str:
                cfg["cookie"] = cookie_str
            conn.execute(
                "UPDATE platform_accounts SET config_json=? WHERE id=?",
                (json.dumps(cfg, ensure_ascii=False), aid)
            )
            conn.commit()
        conn.close()
    except Exception:
        pass


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
        cookies_json = cfg.get("cookies_json", "")
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

        # ── SSO 检测（数据驱动，从探索JSON读取）──
        # SSO 体系（如 JLC passport.jlc.com）的服务端 session 在浏览器关闭后失效，
        # 注入旧 cookie 永远不可能成功，必须做即时密码登录替代
        report = _load_platform_report(acct.get("platform", ""))
        sso_info = report.get("sso_ecosystem", {})
        if sso_info.get("requires_structured_cookies") or sso_info.get("requires_structured_cookies", False):
            return _verify_sso_via_login(acct, cfg, result, report)

        # ── Playwright 验证（非 SSO 平台：cookie 注入路径）──
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

            if cookie or cookies_json:
                domain = site_url.replace("https://", "").replace("http://", "").split("/")[0]

                # 优先使用结构化 cookies_json（保留 domain/path/secure，铁律#19）
                # JLC SSO 需要 .jlc.com domain，扁平字符串丢失 domain 信息
                if cookies_json:
                    try:
                        cookies_list = json.loads(cookies_json)
                        ctx.add_cookies(cookies_list)
                    except (json.JSONDecodeError, Exception):
                        # 降级到扁平字符串
                        pass
                else:
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

            # ── 数据驱动：从探索报告加载 CSS 选择器指示器 ──
            indicator_cfg = _load_indicator_config(acct.get("platform", ""))
            selector_found = {}
            if indicator_cfg:
                # CSS 选择器检测（avatar, username_display 等）
                for key in ["avatar", "username_display", "logout_element"]:
                    sel_val = indicator_cfg.get(key)
                    if not sel_val:
                        continue
                    selectors = sel_val if isinstance(sel_val, list) else [sel_val]
                    for sel in selectors:
                        try:
                            el = page.query_selector(sel)
                            if el:
                                indicator_name = f"selector:{key}"
                                if indicator_name not in indicators:
                                    indicators.append(indicator_name)
                                selector_found[key] = True
                                break
                        except Exception:
                            pass

                # logout_text 列表检测（文本关键词）
                logout_texts = indicator_cfg.get("logout_text", [])
                for text in logout_texts:
                    if re.search(re.escape(text), body_text):
                        found_name = f"logout_text:{text}"
                        if found_name not in indicators and text not in indicators:
                            indicators.append(found_name)

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

            # 判断登录状态（数据驱动）
            if indicator_cfg:
                # ── 从探索报告配置判断 ──
                required = indicator_cfg.get("required_indicators_for_success", [])
                required_found = True
                for req in required:
                    if req == "avatar":
                        if not selector_found.get("avatar"):
                            required_found = False
                    elif req == "用户名":
                        if not username_found_in_body:
                            required_found = False
                    elif req == "退出":
                        if "退出" not in str(indicators) and "logout_text:退出" not in str(indicators):
                            required_found = False
                    elif req == "注销":
                        if "注销" not in str(indicators) and "logout_text:注销" not in str(indicators):
                            required_found = False
                    else:
                        # 通用：检查是否有任何 indicator 包含该关键词
                        if req not in str(indicators):
                            required_found = False
                is_logged_in = not redirected_to_login and required_found
                has_exit_or_logout = "退出" in str(indicators) or "注销" in str(indicators)
            else:
                # ── 无探索报告配置时：fallback 到原严格逻辑 ──
                has_exit_or_logout = any(kw in str(indicators) for kw in ["退出", "注销"])
                is_logged_in = (
                    not redirected_to_login
                    and has_exit_or_logout
                    and (
                        len(indicators) >= 2
                        or username_found_in_body
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
