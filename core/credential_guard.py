"""FlashSloth — 凭证守护脚本
每 30 分钟运行一次：
1. 清理过期的扫码登录 session（超过 300 秒的）
2. 检查所有已保存的凭证是否过期
3. 报告凭证健康状态
4. 清理孤立 session 资源

用法: python3 -B core/credential_guard.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── 配置 ───
SESSION_MAX_AGE = 300       # 5 分钟
CREDENTIAL_EXPIRE_DAYS = 30 # 凭证默认 30 天后过期
WARN_BEFORE_EXPIRE = 7      # 提前 7 天告警


def clean_scan_sessions():
    """清理过期的扫码登录 session"""
    try:
        from flashsloth.core.credential_provider import ScanLoginEngine
        # 获取所有 session 信息（通过模块内部的 session 字典）
        from flashsloth.core.credential_provider import _scan_login_sessions
        cleaned = 0
        expired_ids = []
        now = time.time()
        for sid, sess in list(_scan_login_sessions.items()):
            created = sess.get("created_at", 0)
            if now - created > SESSION_MAX_AGE:
                expired_ids.append(sid)

        for sid in expired_ids:
            ScanLoginEngine.close_scan_login(sid)
            cleaned += 1

        return {"cleaned": cleaned, "remaining": len(_scan_login_sessions)}
    except Exception as e:
        return {"error": str(e)[:100]}


def check_credentials():
    """检查所有凭证的健康状态"""
    try:
        from flashsloth.core.database import get_db, DB_PATH

        conn = get_db()
        accounts = conn.execute(
            "SELECT id, platform, account_name, config_json, is_active, user_id "
            "FROM platform_accounts ORDER BY platform"
        ).fetchall()
        conn.close()

        from flashsloth.core.credential_provider import get_credential, verify_credential

        report = {
            "total": len(accounts),
            "active": 0,
            "inactive": 0,
            "with_credential": 0,
            "valid": 0,
            "expired": 0,
            "uncertain": 0,
            "invalid": 0,
            "details": [],
            "warnings": [],
        }

        for acct in accounts:
            acct = dict(acct)
            if acct["is_active"]:
                report["active"] += 1
            else:
                report["inactive"] += 1

            cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
            has_cookie = bool(cfg.get("cookie", ""))
            if not has_cookie:
                continue

            report["with_credential"] += 1

            # 检查过期时间
            expires_at = cfg.get("expires_at", "")
            capture_time = cfg.get("captured_at", "")
            credential_type = cfg.get("credential_type", "unknown")

            detail = {
                "account_id": acct["id"],
                "platform": acct["platform"],
                "account_name": acct["account_name"],
                "credential_type": credential_type,
                "captured_at": capture_time,
                "expires_at": expires_at,
                "is_active": acct["is_active"],
            }

            # 过期检查
            if expires_at:
                try:
                    exp = datetime.fromisoformat(expires_at)
                    now = datetime.now()
                    if now > exp:
                        detail["status"] = "expired"
                        report["expired"] += 1
                        report["details"].append(detail)
                        continue
                    # 即将过期告警
                    days_left = (exp - now).days
                    if days_left <= WARN_BEFORE_EXPIRE:
                        warn_msg = f"⚠️ {acct['platform']}/{acct['account_name']} 凭证 {days_left} 天后过期"
                        report["warnings"].append(warn_msg)
                except Exception:
                    pass

            # 平台级验证（调用 verify_credential）
            try:
                vr = verify_credential(acct["platform"], acct["id"], acct["user_id"])
                if vr.get("valid") is True:
                    detail["status"] = "valid"
                    report["valid"] += 1
                elif vr.get("valid") is False:
                    detail["status"] = "invalid"
                    detail["verify_message"] = vr.get("message", "")
                    report["invalid"] += 1
                else:
                    detail["status"] = "uncertain"
                    detail["verify_message"] = vr.get("message", "")
                    report["uncertain"] += 1
            except Exception as e:
                detail["status"] = "verify_error"
                detail["verify_message"] = str(e)[:80]
                report["uncertain"] += 1

            report["details"].append(detail)

        return report

    except Exception as e:
        return {"error": str(e)[:200]}


def main():
    print(f"🔐 凭证守护检查 — {datetime.now().isoformat()}")
    print("=" * 50)

    # 1. 清理过期 session
    sess_result = clean_scan_sessions()
    print(f"📱 Session 清理: 关闭 {sess_result.get('cleaned', 0)} 个过期 session, "
          f"剩余 {sess_result.get('remaining', 0)} 个")

    # 2. 检查凭证
    cred_report = check_credentials()
    if "error" in cred_report:
        print(f"❌ 凭证检查失败: {cred_report['error']}")
        return

    print(f"\n📊 凭证健康报告:")
    print(f"   总账号: {cred_report['total']}")
    print(f"   活跃: {cred_report['active']} / 非活跃: {cred_report['inactive']}")
    print(f"   有凭证: {cred_report['with_credential']}")
    print(f"   ✅ 有效: {cred_report['valid']}")
    print(f"   ❌ 无效: {cred_report['invalid']}")
    print(f"   ⏰ 已过期: {cred_report['expired']}")
    print(f"   ❓ 不确定: {cred_report['uncertain']}")

    if cred_report["warnings"]:
        print(f"\n⚠️  告警 ({len(cred_report['warnings'])}):")
        for w in cred_report["warnings"]:
            print(f"   {w}")

    # 汇总摘要（给项目经理用）
    summary = (
        f"凭证守护 | 总{cred_report['total']} | "
        f"✅有效{cred_report['valid']} ❌无效{cred_report['invalid']} "
        f"⏰过期{cred_report['expired']} ❓不确定{cred_report['uncertain']} | "
        f"清理session{sess_result.get('cleaned',0)}"
    )
    print(f"\n📌 {summary}")


if __name__ == "__main__":
    main()
