"""FlashSloth — 论坛探索数据管理路由（增强版）
功能：
  - 板块信息展示
  - 平台发布能力展示（发帖/视频/商品规则+附件限制）
  - 标签栏目（关心板块+关键词）
  - 管理配置预留
"""
from flashsloth.routes._app import app

import json
from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from flashsloth.core.database import get_db


def _normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    if d.startswith("www."):
        d = d[4:]
    return d


@app.route("/exploration")
@login_required
def exploration_page():
    """探索数据管理页面（增强版）"""
    conn = get_db()

    # 从 platform_accounts 获取所有已注册平台
    accounts = conn.execute(
        "SELECT DISTINCT pa.id, pa.platform, pa.config_json, "
        "COALESCE(pa.sort_order, 999) AS sort_order "
        "FROM platform_accounts pa WHERE pa.is_active=1 "
        "ORDER BY sort_order, pa.platform"
    ).fetchall()

    explored = set()
    for r in conn.execute("SELECT DISTINCT platform_domain FROM forum_exploration").fetchall():
        explored.add(_normalize_domain(r["platform_domain"]))

    # 构建平台列表
    all_platforms = []
    seen = set()
    for a in accounts:
        try:
            cfg = json.loads(a["config_json"]) if isinstance(a["config_json"], str) else {}
        except:
            cfg = {}
        raw_domain = cfg.get("site_url", "").replace("https://", "").replace("http://", "").split("/")[0] if cfg.get("site_url") else a["platform"]
        norm_domain = _normalize_domain(raw_domain)
        key = (a["platform"], norm_domain)
        if key in seen:
            continue
        seen.add(key)
        has_data = norm_domain in explored
        all_platforms.append({
            "platform": a["platform"],
            "domain": raw_domain,
            "norm_domain": norm_domain,
            "has_data": has_data,
            "count": 0,
            "sections": [],
            "capabilities": None,
            "tags_of_interest": [],
        })

    # 补充有探索数据但不在accounts中的平台
    for r in conn.execute("SELECT DISTINCT platform, platform_domain FROM forum_exploration").fetchall():
        norm_domain = _normalize_domain(r["platform_domain"])
        key = (r["platform"], norm_domain)
        if key not in seen:
            seen.add(key)
            all_platforms.append({
                "platform": r["platform"],
                "domain": r["platform_domain"],
                "has_data": True,
                "count": 0,
                "sections": [],
                "capabilities": None,
                "tags_of_interest": [],
            })

    # 加载每个平台的探索数据 + 能力配置 + 标签
    for p in all_platforms:
        if p["has_data"]:
            # 使用归一化域名查询（forum_exploration 中域名无 www 前缀）
            query_domain = p["norm_domain"]

            # 总数
            count = conn.execute(
                "SELECT COUNT(*) FROM forum_exploration WHERE platform_domain=?",
                (query_domain,)
            ).fetchone()[0]
            p["count"] = count

            # 只取最近修改的 20 条（其余通过AJAX分页加载）
            sections = conn.execute(
                "SELECT * FROM forum_exploration WHERE platform_domain=? ORDER BY section_id LIMIT 20",
                (query_domain,)
            ).fetchall()
            p["sections"] = [dict(s) for s in sections]

            # 从 forum_exploration 读取 tags_of_interest
            tags_set = set()
            for s in p["sections"]:
                try:
                    toi = json.loads(s["tags_of_interest"]) if isinstance(s.get("tags_of_interest"), str) else []
                    if isinstance(toi, list):
                        tags_set.update(toi)
                except:
                    pass
            p["tags_of_interest"] = sorted(tags_set)

        # 加载平台能力配置
        cap_row = conn.execute(
            "SELECT config_json FROM platform_config WHERE platform_domain=?",
            (p["norm_domain"],)
        ).fetchone()
        if cap_row:
            try:
                p["capabilities"] = json.loads(cap_row["config_json"])
            except:
                pass

    conn.close()

    return render_template("exploration.html",
                         platforms=all_platforms,
                         platforms_json=json.dumps(all_platforms, ensure_ascii=False))


# ─── API: 更新平台能力配置 ─────────────
@app.route("/api/exploration/capabilities/<domain>", methods=["POST"])
@login_required
def api_update_capabilities(domain):
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "无数据"})
    conn = get_db()
    # 找对应平台
    row = conn.execute(
        "SELECT platform FROM forum_exploration WHERE platform_domain=? LIMIT 1",
        (domain,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "平台不存在"})
    plat = row["platform"]
    try:
        conn.execute(
            "INSERT OR REPLACE INTO platform_config (platform, platform_domain, config_json) VALUES (?, ?, ?)",
            (plat, domain, json.dumps(data, ensure_ascii=False))
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "能力配置已更新"})
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "error": str(e)})


# ─── API: 更新标签 ───────────────────
@app.route("/api/exploration/tags/<domain>", methods=["POST"])
@login_required
def api_update_tags(domain):
    data = request.get_json()
    tags = data.get("tags", []) if data else []
    if not isinstance(tags, list):
        tags = [tags]
    tags_json = json.dumps(tags, ensure_ascii=False)
    conn = get_db()
    try:
        conn.execute(
            "UPDATE forum_exploration SET tags_of_interest=? WHERE platform_domain=?",
            (tags_json, domain)
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"标签已更新 ({len(tags)} 个)"})
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "error": str(e)})


# ─── API: 刷新种子数据 ───────────────
@app.route("/api/exploration/reseed", methods=["POST"])
@login_required
def api_reseed_exploration():
    conn = get_db()
    from flashsloth.core.database import _seed_forum_exploration
    _seed_forum_exploration(conn)
    conn.close()
    return jsonify({"success": True, "message": "种子数据已重新加载"})


# ─── API: 分页加载板块列表 ────────────
@app.route("/api/exploration/sections/<domain>")
@login_required
def api_exploration_sections(domain):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)
    offset = (page - 1) * per_page

    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) FROM forum_exploration WHERE platform_domain=?",
        (domain,)
    ).fetchone()[0]
    sections = conn.execute(
        "SELECT * FROM forum_exploration WHERE platform_domain=? ORDER BY section_id LIMIT ? OFFSET ?",
        (domain, per_page, offset)
    ).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "domain": domain,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": max(1, (total + per_page - 1) // per_page),
        "sections": [dict(s) for s in sections],
    })


# ─── 原有API: 单条更新 ───────────────
@app.route("/api/exploration/<int:fid>", methods=["POST"])
@login_required
def api_update_exploration(fid):
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "无数据"})
    conn = get_db()
    row = conn.execute("SELECT * FROM forum_exploration WHERE id=?", (fid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "记录不存在"})
    update_fields = {}
    for field in ["section_name", "can_post", "keywords", "extra_info", "tags_of_interest"]:
        if field in data:
            if field in ("keywords", "extra_info", "tags_of_interest"):
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
        set_clause = ", ".join(f"{k}=?" if k != "updated_at" else f"{k}=datetime('now')" for k in update_fields)
        values = [v for k, v in update_fields.items() if k != "updated_at"]
        values.append(fid)
        conn.execute(f"UPDATE forum_exploration SET {set_clause} WHERE id=?", values)
        conn.commit()
    conn.close()
    return jsonify({"success": True, "updated": list(update_fields.keys())})


# ─── 原有API: 从JSON同步 ─────────────
@app.route("/api/exploration/sync/<domain>", methods=["POST"])
@login_required
def api_sync_exploration(domain):
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
    return jsonify({"success": True, "domain": domain, "sections": sections, "count": len(sections)})


# ─── 原有API: 自定义探索 ──────────────
@app.route("/api/exploration/custom", methods=["POST"])
@login_required
def api_custom_explore():
    data = request.get_json() or {}
    domain = data.get("domain", "").strip()
    platform = data.get("platform", "discuz")
    if not domain:
        return jsonify({"success": False, "error": "请输入网站域名"})
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM forum_exploration WHERE platform_domain=?", (domain,)).fetchone()[0]
    conn.close()
    if existing > 0:
        return jsonify({"success": False, "error": f"'{domain}' 已有 {existing} 条探索数据"})
    return jsonify({"success": True, "message": f"自定义探索 '{domain}' 已提交到后台队列"})
