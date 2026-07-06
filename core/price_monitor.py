"""FlashSloth — 价格监控模块（LCSC/JLC元器件价格）
支持：搜索元件 → 记录价格 → 价格变化报警
"""
import json, re, time, sqlite3
from datetime import datetime
from typing import Optional


def query_lcsc_price(lcsc_code: str) -> Optional[dict]:
    """通过 LCSC 商品页查询元件价格
    返回 {"name", "price", "stock", "package", "manufacturer"}
    """
    import requests
    url = f"https://www.lcsc.com/product-detail/{lcsc_code}.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        html = r.text
        result = {"lcsc_code": lcsc_code, "url": url, "fetched_at": datetime.now().isoformat()}

        # 解析价格
        m = re.search(r'产品型号[：:]\s*([^<]+)', html)
        if m: result["name"] = m.group(1).strip()

        m = re.search(r'(\d+\.?\d*)\s*[-~]\s*(\d+\.?\d*)\s*元', html)
        if m:
            result["price_min"] = float(m.group(1))
            result["price_max"] = float(m.group(2))

        m = re.search(r'库存[：:]\s*(\d+)', html)
        if m: result["stock"] = int(m.group(1))

        m = re.search(r'封装[：:]\s*([^<]+)', html)
        if m: result["package"] = m.group(1).strip()

        m = re.search(r'品牌[：:]\s*([^<]+)', html)
        if m: result["manufacturer"] = m.group(1).strip()

        return result
    except Exception:
        return None


def init_price_db():
    """初始化价格监控表"""
    from flashsloth.core.database import get_db
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS price_monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER DEFAULT 0,
            name TEXT NOT NULL,
            lcsc_code TEXT NOT NULL,
            datasheet_url TEXT DEFAULT '',
            target_price REAL DEFAULT 0,
            alert_enabled INTEGER DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monitor_id INTEGER NOT NULL,
            price_min REAL,
            price_max REAL,
            stock INTEGER,
            fetched_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    # 迁移：添加 price_capable 列到 platform_accounts
    try:
        conn.execute("ALTER TABLE platform_accounts ADD COLUMN price_capable INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    conn.close()


def fetch_and_record(monitor_id: int, lcsc_code: str) -> dict:
    """抓取价格并记录到 history 表"""
    from flashsloth.core.database import get_db
    data = query_lcsc_price(lcsc_code)
    if not data:
        return {"success": False, "error": "抓取失败"}

    conn = get_db()
    conn.execute(
        "INSERT INTO price_history (monitor_id, price_min, price_max, stock) VALUES (?, ?, ?, ?)",
        (monitor_id, data.get("price_min"), data.get("price_max"), data.get("stock"))
    )
    conn.execute(
        "UPDATE price_monitors SET updated_at=datetime('now') WHERE id=?",
        (monitor_id,)
    )
    conn.commit()
    conn.close()

    return {"success": True, "data": data}
