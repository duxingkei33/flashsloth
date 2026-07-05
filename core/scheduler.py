"""FlashSloth 签到调度器 — 定期检查并执行签到

从 admin.py 提取，保持 100% 兼容。
"""
import os, json, time, random, threading
from datetime import datetime

from flashsloth.core.database import get_db

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
    """每分钟执行一次：检查签到 + 状态更新"""
    try:
        from flashsloth.core.signin import get_signin_for_account
    except ImportError:
        return  # signin模块不可用，跳过

    db = get_db()
    accounts = db.execute(
        "SELECT * FROM platform_accounts WHERE is_active=1"
    ).fetchall()
    db.close()

    for acct in accounts:
        try:
            d = dict(acct)
            cfg = json.loads(d.get("config_json") or "{}")
            d["config"] = cfg
            plugin = get_signin_for_account(d)
            if plugin:
                plugin.signin()
        except Exception as e:
            print(f"[Scheduler] {acct.get('platform','?')}/{acct['id']} 签到失败: {e}")
