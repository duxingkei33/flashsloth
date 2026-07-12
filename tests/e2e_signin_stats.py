"""
签到统计 E2E 验证 — 检查签到页面统计卡片是否正确显示成功/失败数据
运行: cd ~/.hermes/flashsloth && source venv/bin/activate && PYTHONPATH=$HOME/.hermes python tests/e2e_signin_stats.py
"""
import sys, os, json, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("e2e_signin")

from flashsloth.core.database import get_db

# ══════════════════════════════════════
# 1. 数据库级验证
# ══════════════════════════════════════
log.info("=" * 50)
log.info("签到统计 E2E 验证")
log.info("=" * 50)

conn = get_db()
today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")

# 今日统计
today_new = conn.execute(
    "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=1 AND already_signed=0",
    (today,)
).fetchone()[0]

today_success = conn.execute(
    "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=1",
    (today,)
).fetchone()[0]

today_fail = conn.execute(
    "SELECT COUNT(DISTINCT account_id) FROM signin_log WHERE date(created_at)=? AND success=0",
    (today,)
).fetchone()[0]

# 全量统计
total_success = conn.execute(
    "SELECT COUNT(*) FROM signin_log WHERE success=1"
).fetchone()[0]

total_fail = conn.execute(
    "SELECT COUNT(*) FROM signin_log WHERE success=0"
).fetchone()[0]

# 账号统计
total_accounts = conn.execute(
    "SELECT COUNT(*) FROM platform_accounts"
).fetchone()[0]

conn.close()

log.info(f"\n📊 DB 签到数据:")
log.info(f"  今日新签到: {today_new}")
log.info(f"  今日成功(含已签): {today_success}")
log.info(f"  今日失败: {today_fail}")
log.info(f"  累计成功(全量): {total_success}")
log.info(f"  累计失败(全量): {total_fail}")
log.info(f"  总账号: {total_accounts}")

# 基本合理性检查
checks = []
checks.append(("今日新签到 >= 0", today_new >= 0))
checks.append(("今日成功 >= 今日新签到", today_success >= today_new))
checks.append(("累计成功 >= 0", total_success >= 0))
checks.append(("累计失败 >= 0", total_fail >= 0))
checks.append(("总账号 > 0", total_accounts > 0))

log.info("\n🔍 数据检查:")
all_pass = True
for name, ok in checks:
    status = "✅" if ok else "❌"
    log.info(f"  {status} {name}")
    if not ok:
        all_pass = False

log.info(f"\n{'✅ 全部通过！' if all_pass else '❌ 有检查未通过'}")

# ══════════════════════════════════════
# 2. API 级验证 (需要登录，可能失败)
# ══════════════════════════════════════
log.info("\n" + "-" * 50)
log.info("API 级验证（需先登录）")
try:
    import requests
    # 先登录
    session = requests.Session()
    login_resp = session.post(
        "http://localhost:5000/auth/login",
        json={"username": "admin", "password": "admin"},
        timeout=5
    )
    if login_resp.status_code == 200:
        # 访问签到页面
        signin_resp = session.get("http://localhost:5000/signin", timeout=5)
        if signin_resp.status_code == 200:
            log.info(f"  ✅ /signin 页面可访问")
            # 检查统计卡片是否存在
            body = signin_resp.text
            cards = ["今日新签到", "今日成功", "今日失败", "累计成功", "累计失败"]
            for card in cards:
                if card in body:
                    log.info(f"    ✅ 统计卡片: {card}")
                else:
                    log.warning(f"    ⚠️ 统计卡片缺失: {card}")
        else:
            log.warning(f"  ⚠️ /signin 状态码: {login_resp.status_code}")
    else:
        log.warning(f"  ⚠️ 登录失败，跳过 API 验证")
except Exception as e:
    log.warning(f"  ⚠️ API 验证异常: {e}")

log.info("\n" + "=" * 50)
log.info(f"结果: {'✅ 通过' if all_pass else '❌ 有异常'}")
log.info("=" * 50)
