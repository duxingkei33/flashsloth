"""FlashSloth — 价格监控路由"""
from flashsloth.routes._app import app
import json
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.price_monitor import fetch_and_record, init_price_db


@app.route("/price-monitor")
@login_required
def price_monitor_page():
    init_price_db()
    conn = get_db()
    monitors = conn.execute(
        "SELECT * FROM price_monitors WHERE user_id=? ORDER BY updated_at DESC",
        (current_user.id,)
    ).fetchall()

    # 每个元件最近5条价格历史
    histories = {}
    for m in monitors:
        h = conn.execute(
            "SELECT * FROM price_history WHERE monitor_id=? ORDER BY fetched_at DESC LIMIT 5",
            (m["id"],)
        ).fetchall()
        histories[m["id"]] = [dict(x) for x in h]

    conn.close()
    return render_template("price_monitor.html",
                         monitors=[dict(m) for m in monitors],
                         histories=histories)

@app.route("/api/price-monitor/accounts")
@login_required
def api_price_monitor_accounts():
    """获取支持价格监控的平台账号"""
    conn = get_db()
    # 识别支持价格的平台：依赖 price_capable 字段（数据驱动）
    accounts = conn.execute(
        "SELECT id, platform, account_name, price_capable, config_json "
        "FROM platform_accounts "
        "WHERE user_id=? AND is_active=1 AND price_capable=1 "
        "ORDER BY platform",
        (current_user.id,)
    ).fetchall()
    conn.close()
    result = []
    for a in accounts:
        result.append({
            "id": a["id"],
            "platform": a["platform"],
            "account_name": a["account_name"],
            "price_capable": a.get("price_capable", 0) or 1,
        })
    return jsonify({"success": True, "accounts": result})


@app.route("/api/price-monitor/add", methods=["POST"])
@login_required
def api_price_monitor_add():
    init_price_db()
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    lcsc_code = data.get("lcsc_code", "").strip()
    target_price = float(data.get("target_price", 0))
    if not name or not lcsc_code:
        return jsonify({"success": False, "error": "元件名和LCSC编码不能为空"})

    conn = get_db()
    conn.execute(
        "INSERT INTO price_monitors (user_id, name, lcsc_code, target_price) VALUES (?, ?, ?, ?)",
        (current_user.id, name, lcsc_code, target_price)
    )
    conn.commit()
    mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    # 立即抓取一次
    result = fetch_and_record(mid, lcsc_code)
    return jsonify({"success": True, "monitor_id": mid, "fetch": result})


@app.route("/api/price-monitor/refresh/<int:mid>", methods=["POST"])
@login_required
def api_price_monitor_refresh(mid):
    init_price_db()
    conn = get_db()
    m = conn.execute(
        "SELECT * FROM price_monitors WHERE id=? AND user_id=?", (mid, current_user.id)
    ).fetchone()
    conn.close()
    if not m:
        return jsonify({"success": False, "error": "不存在的监控项"})

    result = fetch_and_record(mid, m["lcsc_code"])
    return jsonify(result)


@app.route("/api/price-monitor/delete/<int:mid>", methods=["POST"])
@login_required
def api_price_monitor_delete(mid):
    conn = get_db()
    conn.execute("DELETE FROM price_history WHERE monitor_id=?", (mid,))
    conn.execute("DELETE FROM price_monitors WHERE id=? AND user_id=?", (mid, current_user.id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/price-monitor/history/<int:mid>")
@login_required
def api_price_monitor_history(mid):
    init_price_db()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM price_history WHERE monitor_id=? ORDER BY fetched_at DESC LIMIT 30",
        (mid,)
    ).fetchall()
    conn.close()
    return jsonify({"success": True, "history": [dict(r) for r in rows]})
