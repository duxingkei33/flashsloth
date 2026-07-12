"""
FlashSloth 账号状态缓存系统

三层架构：
1. 内存缓存（TTL: 5分钟）— 最快，秒级返回
2. SQLite持久化缓存 — 进程重启后也能读
3. 实时检测（API轻量 → Playwright兜底）

缓存键: f"status:{account_id}"
缓存值: 检测结果 dict（JSON序列化）
"""

import json
import time
import os
import sqlite3
import threading
from datetime import datetime
from typing import Optional

# ─── 内存缓存 ─────────────────────────────────────
_cache: dict[str, dict] = {}  # key -> {data, cached_at}
_cache_lock = threading.Lock()
STATUS_CACHE_TTL = 300  # 5分钟

# SQLite 缓存表
CACHE_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "status_cache.db")


def _ensure_cache_db():
    """确保缓存数据库和表存在"""
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS status_cache (
            cache_key TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            cached_at REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_ensure_cache_db()


# ─── 公共 API ─────────────────────────────────────

def get_status(account_id: int) -> Optional[dict]:
    """从缓存获取状态（先内存 → 后SQLite）"""
    key = f"status:{account_id}"
    
    # 1. 内存缓存
    with _cache_lock:
        entry = _cache.get(key)
        if entry:
            age = time.time() - entry["cached_at"]
            if age < STATUS_CACHE_TTL:
                data = entry["data"].copy()
                data["_cached_at"] = entry["cached_at"]
                data["_cache_age_seconds"] = int(age)
                data["_cache_source"] = "memory"
                return data
            else:
                # 过期了，移除
                del _cache[key]
    
    # 2. SQLite缓存
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT data_json, cached_at FROM status_cache WHERE cache_key=?",
            (key,)
        ).fetchone()
        conn.close()
        
        if row:
            age = time.time() - row["cached_at"]
            if age < STATUS_CACHE_TTL:
                data = json.loads(row["data_json"])
                data["_cached_at"] = row["cached_at"]
                data["_cache_age_seconds"] = int(age)
                data["_cache_source"] = "sqlite"
                # 预热内存缓存
                with _cache_lock:
                    _cache[key] = {"data": data.copy(), "cached_at": row["cached_at"]}
                return data
    except Exception:
        pass
    
    return None


def set_status(account_id: int, data: dict):
    """写入缓存（内存 + SQLite）"""
    key = f"status:{account_id}"
    now = time.time()
    
    # 清理敏感字段再缓存
    clean = {}
    for k, v in data.items():
        if k in ("cookie", "password", "token", "secret"):
            continue
        if k.startswith("cfg_"):
            continue
        clean[k] = v
    
    # 写入内存
    with _cache_lock:
        _cache[key] = {"data": clean, "cached_at": now}
    
    # 写入SQLite
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO status_cache (cache_key, data_json, cached_at) VALUES (?, ?, ?)",
            (key, json.dumps(clean, ensure_ascii=False), now)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    
    # 同时写入 platform_accounts 的 last_status_check
    try:
        from flashsloth.core.database import get_db
        db = get_db()
        db.execute(
            "UPDATE platform_accounts SET status=?, last_status_check=datetime('now') WHERE id=?",
            (json.dumps(clean, ensure_ascii=False), account_id)
        )
        db.commit()
        db.close()
    except Exception:
        pass


def invalidate(account_id: int):
    """清除指定账号的缓存"""
    key = f"status:{account_id}"
    with _cache_lock:
        _cache.pop(key, None)
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        conn.execute("DELETE FROM status_cache WHERE cache_key=?", (key,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_all_cached() -> dict[int, dict]:
    """获取所有缓存的账号状态（用于批量展示）"""
    result = {}
    
    # 先读内存
    with _cache_lock:
        for key, entry in _cache.items():
            if key.startswith("status:"):
                aid = int(key.split(":")[1])
                age = time.time() - entry["cached_at"]
                if age < STATUS_CACHE_TTL:
                    data = entry["data"].copy()
                    data["_cached_at"] = entry["cached_at"]
                    data["_cache_age_seconds"] = int(age)
                    data["_cache_source"] = "memory"
                    result[aid] = data
    
    # 从 SQLite 补充缺失的
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT cache_key, data_json, cached_at FROM status_cache"
        ).fetchall()
        conn.close()
        
        for row in rows:
            key = row["cache_key"]
            if not key.startswith("status:"):
                continue
            aid = int(key.split(":")[1])
            if aid in result:
                continue  # 已经在内存缓存中
            
            age = time.time() - row["cached_at"]
            if age < STATUS_CACHE_TTL:
                data = json.loads(row["data_json"])
                data["_cached_at"] = row["cached_at"]
                data["_cache_age_seconds"] = int(age)
                data["_cache_source"] = "sqlite"
                result[aid] = data
    except Exception:
        pass
    
    return result


def get_cache_stats() -> dict:
    """获取缓存统计信息"""
    now = time.time()
    mem_count = 0
    mem_valid = 0
    with _cache_lock:
        for key, entry in _cache.items():
            if key.startswith("status:"):
                mem_count += 1
                if (now - entry["cached_at"]) < STATUS_CACHE_TTL:
                    mem_valid += 1
    
    sqlite_count = 0
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        sqlite_count = conn.execute(
            "SELECT COUNT(*) FROM status_cache"
        ).fetchone()[0]
        conn.close()
    except Exception:
        pass
    
    return {
        "memory_entries": mem_count,
        "memory_valid": mem_valid,
        "sqlite_entries": sqlite_count,
        "cache_ttl_seconds": STATUS_CACHE_TTL,
    }
