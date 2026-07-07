"""FlashSloth 签到调度器 — 定期检查并执行签到

从 admin.py 提取，保持 100% 兼容。
在设定的签到时间（默认 08:00）起 1 小时窗口内随机执行。
"""
import os, json, time, random, threading
from datetime import datetime

from flashsloth.core.database import get_db
from flashsloth.core.notifier import notify_info, notify_warn, notify_error
from flashsloth.core.credential_crypto import decrypt_config
# 调度器状态
_scheduler_running = False
_scheduler_stop = threading.Event()
_scheduler_thread = None

# 对外导出兼容别名（signin.py 等引用）
scheduler_running = _scheduler_running
scheduler_stop = _scheduler_stop


def start_scheduler():
    """启动签到后台调度器（守护线程，每分钟检查）"""
    global _scheduler_running, _scheduler_thread
    if _scheduler_running:
        return
    _scheduler_running = True
    _scheduler_stop.clear()

    def _loop():
        global _scheduler_running
        # 启动时随机延迟 0~120 秒，避免多台实例同时签到
        _scheduler_stop.wait(random.randint(0, 120))
        while not _scheduler_stop.is_set():
            try:
                _tick_scheduler()
            except Exception as e:
                print(f"[Scheduler] 调度异常: {e}")
            _scheduler_stop.wait(60)
        _scheduler_running = False

    _scheduler_thread = threading.Thread(target=_loop, daemon=True, name="fs-scheduler")
    _scheduler_thread.start()


def stop_scheduler():
    """停止调度器"""
    global _scheduler_running
    _scheduler_stop.set()
    _scheduler_running = False


def _tick_scheduler():
    """每分钟执行一次：检查每个启用的账号是否需要签到

    逻辑与 v3.2.1 一致：
      1. 检查全局自动签到是否启用
      2. 获取每个账号的签到时间（默认 08:00）
      3. 只在 [签到时间, 签到时间+1小时) 窗口内执行
      4. 检查该账号今天是否已签过（从 signin_log 判断）
      5. 执行签到并记录日志
    """
    try:
        from flashsloth.core.signin import get_signin_for_account
    except ImportError:
        return  # signin 模块不可用，跳过

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    now_minutes = now.hour * 60 + now.minute

    db = get_db()

    # 1. 检查全局是否启用了自动签到
    sched = db.execute(
        "SELECT config_json FROM provider_config WHERE provider_type='signin_schedule' LIMIT 1"
    ).fetchone()
    if not sched:
        db.close()
        return
    sched_cfg = json.loads(sched["config_json"]) if sched["config_json"] else {}
    if not sched_cfg.get("enabled", False):
        db.close()
        return

    # 2. 获取所有活跃账号
    accounts = db.execute(
        "SELECT * FROM platform_accounts WHERE is_active=1 ORDER BY platform, account_name"
    ).fetchall()
    db.close()

    for acct in accounts:
        try:
            d = dict(acct)
            cfg = json.loads(d.get("config_json") or "{}")
            decrypt_config(cfg)  # 解密凭证用于签到
            d["config"] = cfg

            # 跳过禁用签到的账号
            if not cfg.get("signin_enabled", True):
                continue

            # 3. 获取签到时间，计算窗口
            signin_time_str = cfg.get("signin_time", "08:00")
            parts = signin_time_str.split(":")
            base_hour = int(parts[0]) if len(parts) > 0 else 8
            base_min = int(parts[1]) if len(parts) > 1 else 0
            base_minutes = base_hour * 60 + base_min

            # 时间窗口：从设定的时间开始，之后随机 1 小时
            window_start = base_minutes
            window_end = base_minutes + 60

            if not (window_start <= now_minutes < window_end):
                continue  # 不在时间窗口内

            # 每个账号在窗口内的随机偏移（避免同时触发）
            # 基于 account_id 生成确定性偏移，确保同一账号在同一 tick 内不重复跑
            acct_rand_offset = (d["id"] * 7 + 13) % 45  # 0~44 分钟偏移
            # 只在当前分钟接近该账号的随机目标时间时才执行
            target_minute = window_start + acct_rand_offset
            # 允许 ±1 分钟的误差（scheduler 每分钟 tick 一次）
            if not (target_minute - 1 <= now_minutes <= target_minute + 1):
                continue

            # 4. 检查当天是否已经签过
            from plugins.forum_signin import ensure_signin_log_table
            ensure_signin_log_table()

            # 使用一个新连接检查，避免 db 连接冲突
            check_db = get_db()
            log_exists = check_db.execute(
                "SELECT COUNT(*) FROM signin_log WHERE account_id=? AND date(created_at)=? AND success=1 AND already_signed=0",
                (d["id"], today_str)
            ).fetchone()[0]
            check_db.close()

            if log_exists > 0:
                continue  # 今天已经签过

            # 5. 检查是否有签到插件
            plugin = get_signin_for_account(d)
            if not plugin:
                continue

            # 6. 执行签到
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(plugin.signin)
                try:
                    result = fut.result(timeout=30)
                except concurrent.futures.TimeoutError:
                    result = {"success": False, "already_signed": False,
                              "error": "超时", "message": ""}
                except Exception as e:
                    result = {"success": False, "already_signed": False,
                              "error": str(e), "message": ""}

            # 7. 记录日志
            site_url = cfg.get("site_url", "")
            from plugins.forum_signin import log_signin
            log_signin(
                account_id=d["id"],
                platform=d["platform"],
                account_name=d["account_name"],
                site_url=site_url,
                success=result.get("success", False),
                already_signed=result.get("already_signed", False),
                error=result.get("error", ""),
                message=result.get("message", ""),
            )

            if result.get("success", False):
                if result.get("already_signed", False):
                    print(f"[Scheduler] {d['platform']}/{d['account_name']} — 今天已签到")
                else:
                    print(f"[Scheduler] {d['platform']}/{d['account_name']} — 签到成功")
            else:
                print(f"[Scheduler] {d['platform']}/{d['account_name']} — 签到失败: {result.get('error', '')}")

        except Exception as e:
            print(f"[Scheduler] {acct.get('platform','?')}/{acct['id']} 签到失败: {e}")
