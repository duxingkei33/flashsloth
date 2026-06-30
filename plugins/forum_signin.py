"""
论坛每日签到 — FlashSloth 插件
支持 Discuz! 论坛的 k_misign 插件签到系统
由 Hermes cron 调度，随机白天时间执行
"""
import re, json, sqlite3, sys, os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from flashsloth.plugins.browser_session import HumanSession
except ImportError:
    from plugins.browser_session import HumanSession

CST = timezone(timedelta(hours=8))
DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def load_account(account_id: int):
    """加载指定账号配置"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND is_active=1",
        (account_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["config"] = json.loads(d.get("config_json", "{}"))
    return d


def do_signin(account) -> dict:
    """执行签到，返回结果"""
    site_url = account["config"].get("site_url", "").rstrip("/")
    cookie = account["config"].get("cookie", "")
    username = account["config"].get("username", account["account_name"])

    if not site_url or not cookie:
        return {"success": False, "error": "缺少 site_url 或 cookie"}

    browser = HumanSession(base_url=site_url, min_delay=0.5, max_delay=2.0)
    browser.set_cookies(cookie)

    # 1. 先访问签到页面获取 formhash
    sign_url = site_url.rstrip("/") + "/k_misign-sign.html"
    resp = browser.get(sign_url)

    # 检查登录状态
    uid_match = re.search(r"discuz_uid\s*=\s*'(\d+)'", resp.text)
    if not uid_match or uid_match.group(1) == "0":
        return {"success": False, "error": "Cookie 无效，未登录"}

    # 检查是否已签到（不同论坛格式不同）
    sign_status_texts = ["已签", "已签到", "签到成功", "今日已签", "您的签到排名"]
    already_signed = any(t in resp.text for t in sign_status_texts)
    if already_signed:
        return {"success": True, "error": "", "already_signed": True,
                "message": "今天已签到"}

    # 2. 获取 formhash
    formhash = None
    for pattern in [
        r'name="formhash"[^>]+value="([^"]+)"',
        r'formhash\s*=\s*"([^"]+)"',
        r'formhash=([a-zA-Z0-9]+)',
    ]:
        match = re.search(pattern, resp.text)
        if match:
            formhash = match.group(1)
            break

    if not formhash:
        # 尝试从签到链接提取
        link_match = re.search(
            r'k_misign:sign&operation=qiandao&formhash=([a-zA-Z0-9]+)',
            resp.text
        )
        if link_match:
            formhash = link_match.group(1)

    if not formhash:
        return {"success": False, "error": "无法获取 formhash"}

    # 3. 执行签到（AJAX 接口）
    qiandao_url = (
        f"{site_url}/plugin.php?id=k_misign:sign"
        f"&operation=qiandao&formhash={formhash}&format=empty"
    )
    sign_resp = browser.get(qiandao_url)

    # 验证结果：重新加载签到页看是否已签到
    import time
    time.sleep(1)
    verify_resp = browser.get(sign_url)

    sign_status_texts = ["已签", "已签到", "签到成功", "今日已签", "您的签到排名"]
    if any(t in verify_resp.text for t in sign_status_texts):
        return {"success": True, "error": "", "already_signed": False,
                "message": "签到成功 ✅"}

    # 检查 AJAX 返回值
    if sign_resp.text.strip():
        msg = sign_resp.text.strip()[:200]
        # 有些论坛在 XML 里返回签到成功
        if "今日已签" in msg or "签到成功" in msg or "succeed" in msg.lower():
            return {"success": True, "error": "", "already_signed": False,
                    "message": "签到成功 ✅"}
        return {"success": False, "error": f"签到失败: {msg}"}

    return {"success": False, "error": "签到失败，未知原因"}


def main():
    """主入口 — 由 Hermes cron 调用"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"🦥 每日签到 — {now}", ""]

    # 遍历 discuz 平台账号
    conn = get_db()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE platform='discuz' AND is_active=1"
    ).fetchall()
    conn.close()

    any_success = False
    for row in accounts:
        account = dict(row)
        account["config"] = json.loads(account.get("config_json", "{}"))
        site_url = account["config"].get("site_url", "")
        site_name = site_url.replace("https://", "").replace("http://", "").split("/")[0]

        lines.append(f"📡 {account['account_name']} ({site_name})")

        # 快速检查：只有安装 k_misign 插件的论坛才能签到
        import requests as _req
        try:
            test_url = site_url.rstrip("/") + "/k_misign-sign.html"
            check = _req.get(test_url, timeout=5, headers={
                "User-Agent": "Mozilla/5.0"
            })
            if check.status_code != 200 or "k_misign" not in check.text.lower():
                lines.append(f"   ⏭️ 跳过：该论坛未安装 k_misign 签到插件")
                continue
        except Exception:
            lines.append(f"   ⏭️ 跳过：无法访问签到页面")
            continue

        result = do_signin(account)
        if result["success"]:
            any_success = True
            if result.get("already_signed"):
                lines.append(f"   ℹ️ 今天已签到")
            else:
                lines.append(f"   ✅ {result['message']}")
        else:
            lines.append(f"   ❌ {result['error']}")

    if not any_success:
        lines.append("\n⚠️ 所有账号签到均失败，请检查 Cookie 是否有效")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
