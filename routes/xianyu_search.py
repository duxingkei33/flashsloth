"""FlashSloth — 闲鱼搜索路由"""
from flashsloth.routes._app import app

import json
from flask import (render_template, request, jsonify)
from flask_login import login_required, current_user

from flashsloth.core.database import get_db


@app.route("/xianyu/search")
@login_required
def xianyu_search_page():
    """闲鱼搜索页面"""
    conn = get_db()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? AND platform='xianyu' AND is_active=1",
        (current_user.id,)
    ).fetchall()
    conn.close()
    return render_template("xianyu_search.html", accounts=[dict(a) for a in accounts])


@app.route("/api/xianyu/search", methods=["POST"])
@login_required
def api_xianyu_search():
    """闲鱼商品搜索 API"""
    data = request.get_json(force=True, silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    account_id = data.get("account_id", 0)
    page = int(data.get("page", 1))
    page_size = int(data.get("page_size", 20))
    min_price_raw = data.get("min_price")
    max_price_raw = data.get("max_price")
    min_price = float(min_price_raw) if (min_price_raw and float(min_price_raw) > 0) else 0
    max_price = float(max_price_raw) if (max_price_raw and float(max_price_raw) > 0) else 0
    sort_by = data.get("sort_by", "default")

    if not keyword:
        return jsonify({"success": False, "error": "请输入搜索关键词"})

    # 找对应账号的 cookie
    conn = get_db()
    if account_id:
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE id=? AND user_id=? AND platform='xianyu'",
            (account_id, current_user.id)
        ).fetchone()
    else:
        # 取第一个活跃账号
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE user_id=? AND platform='xianyu' AND is_active=1",
            (current_user.id,)
        ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "未找到闲鱼账号，请先在账号管理添加闲鱼账户并配置 Cookie"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    cookie = cfg.get("cookie", "")
    if not cookie:
        return jsonify({"success": False, "error": "闲鱼账号未配置 Cookie，请先通过浏览器登录获取"})

    # 调用 xianyu 适配器搜索
    try:
        from sdk.adapters.xianyu_v2 import XianyuApiV2
        client = XianyuApiV2(cookie)
        products = client.search_products(
            keyword=keyword,
            page=page,
            page_size=page_size,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
        )
        results = []
        for p in products:
            results.append({
                "item_id": p.item_id,
                "title": p.title,
                "price": p.price,
                "original_price": p.original_price,
                "sold_price": p.sold_price,
                "images": p.images[:3] if p.images else [],
                "stock": p.stock,
                "sales": p.sales,
                "seller_name": p.seller_name,
                "seller_credit": p.seller_credit,
                "location": p.location,
                "status": p.status,
                "url": p.url,
            })
        return jsonify({"success": True, "total": len(results), "products": results})
    except Exception as e:
        return jsonify({"success": False, "error": f"搜索失败: {e}"})


@app.route("/api/xianyu/detail/<item_id>")
@login_required
def api_xianyu_detail(item_id):
    """闲鱼商品详情 API"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? AND platform='xianyu' AND is_active=1",
        (current_user.id,)
    ).fetchone()
    conn.close()

    if not acct:
        return jsonify({"success": False, "error": "未找到活跃闲鱼账号"})

    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    cookie = cfg.get("cookie", "")

    try:
        from sdk.adapters.xianyu_v2 import XianyuApiV2
        client = XianyuApiV2(cookie)
        product = client.get_item_info(item_id)
        if product:
            return jsonify({
                "success": True,
                "product": {
                    "item_id": product.item_id,
                    "title": product.title,
                    "desc": product.desc,
                    "price": product.price,
                    "original_price": product.original_price,
                    "images": product.images,
                    "stock": product.stock,
                    "sales": product.sales,
                    "seller_name": product.seller_name,
                    "seller_credit": product.seller_credit,
                    "location": product.location,
                    "status": product.status,
                    "url": product.url,
                    "sku_list": product.sku_list,
                }
            })
        return jsonify({"success": False, "error": "商品不存在"})
    except Exception as e:
        return jsonify({"success": False, "error": f"获取详情失败: {e}"})
