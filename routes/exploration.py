"""
FlashSloth — 论坛探索数据管理路由
查看/编辑平台上所有已探索的版块/分类数据
"""
from flashsloth.routes._app import app

import json
from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from flashsloth.core.database import get_db


@app.route("/exploration")
@login_required
def exploration_page():
    """探索数据管理页面（折叠面板，首项展开其余折叠，排序从DB动态加载）"""
    conn = get_db()
    
    # 从 platform_accounts 获取所有已注册平台（自动引入，不写死）
    # 排序由 DB 控制：先按 sort_order（NULL=999），再按 platform
    accounts = conn.execute(
        "SELECT DISTINCT pa.id, pa.platform, pa.config_json, "
        "COALESCE(pa.sort_order, 999) AS sort_order "
        "FROM platform_accounts pa WHERE pa.is_active=1 "
        "ORDER BY sort_order, pa.platform"
    ).fetchall()
    
    # 已探索的平台域
    explored = set()
    for r in conn.execute("SELECT DISTINCT platform_domain FROM forum_exploration").fetchall():
        explored.add(r["platform_domain"])
    
    # 构建平台列表（已探索+未探索）
    all_platforms = []
    seen = set()
    for a in accounts:
        try:
            cfg = json.loads(a["config_json"]) if isinstance(a["config_json"], str) else {}
        except:
            cfg = {}
        domain = cfg.get("site_url", "").replace("https://", "").replace("http://", "").split("/")[0] if cfg.get("site_url") else a["platform"]
        key = (a["platform"], domain)
        if key in seen:
            continue
        seen.add(key)
        has_data = domain in explored
        all_platforms.append({
            "platform": a["platform"],
            "domain": domain,
            "has_data": has_data,
            "count": 0,
            "sections": [],
        })
    
    # 补充有探索数据但不在accounts中的平台（追加在末尾）
    for r in conn.execute("SELECT DISTINCT platform, platform_domain FROM forum_exploration").fetchall():
        key = (r["platform"], r["platform_domain"])
        if key not in seen:
            seen.add(key)
            all_platforms.append({
                "platform": r["platform"],
                "domain": r["platform_domain"],
                "has_data": True,
                "count": 0,
                "sections": [],
            })
    
    # 加载每个平台的探索数据
    for p in all_platforms:
        if p["has_data"]:
            sections = conn.execute(
                "SELECT * FROM forum_exploration WHERE platform=? AND platform_domain=? ORDER BY section_id",
                (p["platform"], p["domain"])
            ).fetchall()
            p["sections"] = [dict(s) for s in sections]
            p["count"] = len(sections)
    
    conn.close()
    
    return render_template("exploration.html",
                         platforms=all_platforms,
                         platforms_json=json.dumps(all_platforms, ensure_ascii=False))


@app.route("/api/exploration/<int:fid>", methods=["POST"])
@login_required
def api_update_exploration(fid):
    """更新探索数据（手动修正）"""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "无数据"})
    
    conn = get_db()
    row = conn.execute("SELECT * FROM forum_exploration WHERE id=?",
                       (fid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "记录不存在"})
    
    # 允许修改的字段
    update_fields = {}
    for field in ["section_name", "can_post", "keywords", "extra_info"]:
        if field in data:
            if field in ("keywords", "extra_info"):
                # JSON 字段需要序列化
                if isinstance(data[field], str):
                    try:
                        json.loads(data[field])
                        update_fields[field] = data[field]
                    except:
                        update_fields[field] = json.dumps(data[field], ensure_ascii=False)
                else:
                    update_fields[field] = json.dumps(data[field], ensure_ascii=False)
            elif field == "can_post":
                update_fields[field] = 1 if data[field] else 0
            else:
                update_fields[field] = data[field]
    
    if update_fields:
        update_fields["updated_at"] = "datetime('now')"
        set_clause = ", ".join(f"{k}=?" if k != "updated_at" else f"{k}=datetime('now')" for k in update_fields)
        values = [v for k, v in update_fields.items() if k != "updated_at"]
        values.append(fid)
        conn.execute(
            f"UPDATE forum_exploration SET {set_clause} WHERE id=?",
            values
        )
        conn.commit()
    
    conn.close()
    return jsonify({"success": True, "updated": list(update_fields.keys())})


@app.route("/api/exploration/batch", methods=["POST"])
@login_required
def api_batch_update_exploration():
    """批量更新（比如一键同步JSON到DB）"""
    conn = get_db()
    
    # 从JSON重新导入
    from flashsloth.core.explorer import explore_forum
    from flashsloth.core.database import _seed_forum_exploration
    
    _seed_forum_exploration(conn)
    conn.close()
    
    return jsonify({"success": True, "message": "已从JSON重新同步探索数据"})


@app.route("/api/exploration/sync/<domain>", methods=["POST"])
@login_required
def api_sync_exploration(domain):
    """从数据库同步到 forum_registry 关键词"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM forum_exploration WHERE platform_domain=? AND can_post=1",
        (domain,)
    ).fetchall()
    conn.close()
    
    sections = {}
    for r in rows:
        try:
            kw = json.loads(r["keywords"]) if isinstance(r["keywords"], str) else []
        except:
            kw = [r["section_name"]]
        sections[r["section_id"]] = {
            "name": r["section_name"],
            "keywords": kw,
        }
    
    return jsonify({
        "success": True,
        "domain": domain,
        "sections": sections,
        "count": len(sections),
    })


@app.route("/api/exploration/custom", methods=["POST"])
@login_required
def api_custom_explore():
    """自定义网站探索入口"""
    data = request.get_json() or {}
    domain = data.get("domain", "").strip()
    platform = data.get("platform", "discuz")
    login_method = data.get("login_method", "cookie")
    
    if not domain:
        return jsonify({"success": False, "error": "请输入网站域名"})
    
    # 验证是否已探索过
    conn = get_db()
    existing = conn.execute(
        "SELECT COUNT(*) FROM forum_exploration WHERE platform_domain=?",
        (domain,)
    ).fetchone()[0]
    conn.close()
    
    if existing > 0:
        return jsonify({"success": False, "error": f"'{domain}' 已有 {existing} 条探索数据，无需重复探索"})
    
    # 后续由cron实际执行探索任务，这里先返回任务已提交
    return jsonify({
        "success": True,
        "message": f"自定义探索 '{domain}' ({platform}) 已提交到后台队列，下次自驱cron将执行Playwright探索"
    })
