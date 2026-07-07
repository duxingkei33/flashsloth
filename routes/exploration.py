"""FlashSloth — 论坛探索数据管理路由（增强版）
功能：
  - 板块信息展示
  - 平台发布能力展示（发帖/视频/商品规则+附件限制）
  - 标签栏目（关心板块+关键词）
  - 管理配置预留
"""
from flashsloth.routes._app import app

import json, os
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
                "norm_domain": norm_domain,
                "has_data": True,
                "count": 0,
                "sections": [],
                "capabilities": None,
                "tags_of_interest": [],
            })

    # 加载每个平台的探索数据 + 能力配置 + 标签
    for p in all_platforms:
        # 加载登录能力（从 platform_reports JSON）
        _reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_reports")
        _cap_map = {"wechat": "wechat_mp", "xianyu_v2": "xianyu", "xianyu_sidecar": "xianyu", "xianyu_auto_reply": "xianyu", "xianyu_products": "xianyu"}
        json_name = _cap_map.get(p["platform"], p["platform"])
        cap_path = os.path.join(_reports_dir, f"{json_name}_login_capabilities.json")
        if os.path.exists(cap_path):
            try:
                with open(cap_path, "r", encoding="utf-8") as f:
                    p["login_capabilities"] = json.load(f)
            except:
                pass
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
    domain = _normalize_domain(domain)
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
    domain = _normalize_domain(domain)
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
    domain = _normalize_domain(domain)
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
    domain = _normalize_domain(domain)
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


# ─── API: 自定义探索（真Playwright）──────────────
@app.route("/api/exploration/custom", methods=["POST"])
@login_required
def api_custom_explore():
    data = request.get_json() or {}
    domain = data.get("domain", "").strip()
    platform = data.get("platform", "auto")
    if not domain:
        return jsonify({"success": False, "error": "请输入网站域名"})
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM forum_exploration WHERE platform_domain=?", (domain,)).fetchone()[0]
    if existing > 0:
        conn.close()
        return jsonify({"success": False, "error": f"'{domain}' 已有 {existing} 条探索数据，如需重新探索请先删除"})

    # 限流检查（每域名每小时一次）
    from flashsloth.core.explorer import can_explore, get_explore_cooldown
    if not can_explore(domain):
        remaining = get_explore_cooldown(domain)
        return jsonify({
            "success": False, "error": f"探索频率限制: '{domain}' 还需等待 {remaining}s",
            "cooldown_seconds": remaining,
        })

    # 从 platform_accounts 找账号配置
    acct = conn.execute(
        "SELECT config_json FROM platform_accounts WHERE is_active=1 AND user_id=? ORDER BY id LIMIT 1",
        (current_user.id,)
    ).fetchone()
    conn.close()

    # 启动 Playwright 探索（后台进程）
    import subprocess, sys as _sys
    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "pw_explore.py")
    os.makedirs(os.path.dirname(script_path), exist_ok=True)

    # 写探索脚本（使用中央防检测模块）
    script_content = f'''# -*- coding: utf-8 -*-
"""PW explore: {domain}"""
import sys, os, json, time
sys.path.insert(0, "{os.path.dirname(os.path.dirname(__file__))}")
from core.explorer import save_exploration_results, explore_discuz_forums, _detect_platform_type
from core.anti_detect import create_human_context, human_delay, human_wait_page_ready
from flashsloth.core.database import get_db
from playwright.sync_api import sync_playwright

SITE = "https://{domain}"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
    # 使用中央防风模块创建人类模拟上下文
    ctx = create_human_context(browser)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{{get:()=>undefined}})")
    page = ctx.new_page()
    page.goto(SITE, wait_until="domcontentloaded", timeout=30000)
    human_wait_page_ready(page)
    ptype = _detect_platform_type(page)
    print(f"平台类型: {{ptype}}")
    sections = []
    if ptype == "discuz":
        sections = explore_discuz_forums(page, SITE, "{domain}")
    conn = get_db()
    save_exploration_results(conn, "{platform}" if "{platform}" != "auto" else ptype, "{domain}", sections)
    conn.close()
    browser.close()
    print(f"完成: {{len(sections)}} sections")
'''
    with open(script_path, "w") as f:
        f.write(script_content)

    try:
        result = subprocess.run(
            [_sys.executable, script_path],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(__file__))}
        )
        # 清理临时脚本
        try: os.unlink(script_path)
        except: pass

        if result.returncode != 0:
            return jsonify({"success": False, "error": f"探索失败: {result.stderr[-500:]}"})

        # 重新查询结果
        conn = get_db()
        new_count = conn.execute("SELECT COUNT(*) FROM forum_exploration WHERE platform_domain=?", (domain,)).fetchone()[0]
        conn.close()
        return jsonify({
            "success": True,
            "message": f"探索完成: 发现 {new_count} 个版块",
            "domain": domain,
            "sections_count": new_count,
            "log": result.stdout[-500:],
        })
    except subprocess.TimeoutExpired:
        try: os.unlink(script_path)
        except: pass
        return jsonify({"success": False, "error": "探索超时（>120秒），请重试或检查域名是否正确"})
    except Exception as e:
        try: os.unlink(script_path)
        except: pass
        return jsonify({"success": False, "error": f"探索异常: {e}"})


# ─── API: 探索状态自动检测 ──────────────────────
@app.route("/api/exploration/discover-accounts", methods=["GET"])
@login_required
def api_discover_from_accounts():
    """扫描 platform_accounts，返回已探索 / 未探索的平台列表"""
    conn = get_db()
    accounts = conn.execute(
        "SELECT DISTINCT pa.id, pa.platform, pa.account_name, pa.config_json, "
        "COALESCE(pa.sort_order, 999) AS sort_order "
        "FROM platform_accounts pa WHERE pa.is_active=1 "
        "ORDER BY sort_order, pa.platform"
    ).fetchall()

    # 已探索的域名集合
    explored_domains = set()
    for r in conn.execute("SELECT DISTINCT platform_domain FROM forum_exploration").fetchall():
        explored_domains.add(r["platform_domain"].strip().lower())

    results = {"explored": [], "unexplored": []}
    seen = set()
    for a in accounts:
        try:
            cfg = json.loads(a["config_json"]) if isinstance(a["config_json"], str) else {}
        except:
            cfg = {}
        raw_url = cfg.get("site_url", "")
        if not raw_url:
            continue
        domain = raw_url.replace("https://", "").replace("http://", "").split("/")[0].lower()
        if domain.startswith("www."):
            domain = domain[4:]
        key = (a["platform"], domain)
        if key in seen:
            continue
        seen.add(key)
        entry = {
            "platform": a["platform"],
            "account_name": a["account_name"],
            "domain": domain,
            "site_url": raw_url,
        }
        if domain in explored_domains:
            entry["section_count"] = conn.execute(
                "SELECT COUNT(*) FROM forum_exploration WHERE platform_domain=?", (domain,)
            ).fetchone()[0]
            results["explored"].append(entry)
        else:
            results["unexplored"].append(entry)

    conn.close()
    return jsonify({"success": True, **results})


# ─── API: 自动探索未探索的平台 ──────────────────
@app.route("/api/exploration/auto-explore/<domain>", methods=["POST"])
@login_required
def api_auto_explore(domain):
    """对指定域名尝试自动探索：先查 config 预设 JSON，再尝试 Playwright 探索"""
    domain = _normalize_domain(domain)
    conn = get_db()

    # 查这个域名的来源账号
    account = conn.execute(
        "SELECT * FROM platform_accounts WHERE is_active=1 ORDER BY id"
    ).fetchall()

    target_acct = None
    for a in account:
        try:
            cfg = json.loads(a["config_json"]) if isinstance(a["config_json"], str) else {}
        except:
            cfg = {}
        raw_url = cfg.get("site_url", "")
        if not raw_url:
            continue
        d = raw_url.replace("https://", "").replace("http://", "").split("/")[0].lower()
        if d.startswith("www."):
            d = d[4:]
        if d == domain:
            target_acct = dict(a)
            target_acct["config"] = cfg
            break

    if not target_acct:
        conn.close()
        return jsonify({"success": False, "error": f"未找到域名 {domain} 对应的账号"})

    # 尝试从 config/platform_*.json 预设种子
    root = os.path.dirname(os.path.dirname(__file__))
    config_dir = os.path.join(root, "config")

    # 尝试匹配已知预设
    preset_map = {
        "amobbs.com": ("platform_amobbs", "discuz_amobbs"),
        "mydigit.cn": ("platform_mydigit", "discuz_mydigit"),
        "csdn.net": ("platform_csdn", "csdn"),
        "oshwhub.com": ("platform_oshwhub", "oshwhub"),
    }

    if domain in preset_map:
        preset_name, plat = preset_map[domain]
        preset_path = os.path.join(config_dir, f"{preset_name}.json")
        if os.path.exists(preset_path):
            from flashsloth.core.database import _seed_forum_exploration
            _seed_forum_exploration(conn)
            conn.close()
            return jsonify({
                "success": True,
                "message": f"已从预设 {preset_name}.json 加载探索数据",
                "domain": domain,
                "platform": plat,
            })

    conn.close()
    return jsonify({
        "success": True,
        "message": f"'{domain}' 无可用的预设配置，请先运行 Playwright 手动探索",
        "needs_custom_exploration": True,
        "domain": domain,
    })


# ─── API: 保存关心板块配置 ─────────────
@app.route("/api/exploration/interested-sections/<domain>", methods=["POST"])
@login_required
def api_save_interested_sections(domain):
    """保存关心板块配置（section_id + 优先级关键词）"""
    domain = _normalize_domain(domain)
    data = request.get_json() or {}
    section_ids = data.get("section_ids", [])
    if not isinstance(section_ids, list):
        section_ids = [section_ids]

    conn = get_db()
    try:
        # 将关心的板块标记到 tags_of_interest（以 "care:" 前缀标识）
        care_tags = json.dumps([f"care:{sid}" for sid in section_ids], ensure_ascii=False)
        conn.execute(
            "UPDATE forum_exploration SET tags_of_interest=? WHERE platform_domain=?",
            (care_tags, domain)
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": f"已保存 {len(section_ids)} 个关心板块"})
    except Exception as e:
        conn.close()
        return jsonify({"success": False, "error": str(e)})


# ─── API: 获取所有板块关键词（供UI自动提取）──
@app.route("/api/exploration/all-keywords/<domain>")
@login_required
def api_all_keywords(domain):
    """获取指定域名下所有板块的关键词集合"""
    domain = _normalize_domain(domain)
    conn = get_db()
    rows = conn.execute(
        "SELECT section_id, section_name, keywords FROM forum_exploration WHERE platform_domain=? AND can_post=1",
        (domain,)
    ).fetchall()
    conn.close()

    all_keywords = set()
    section_keywords = {}
    for r in rows:
        try:
            kw = json.loads(r["keywords"]) if isinstance(r["keywords"], str) else []
        except:
            kw = [r["section_name"]]
        if isinstance(kw, list):
            all_keywords.update(kw)
        section_keywords[r["section_id"]] = {
            "name": r["section_name"],
            "keywords": kw if isinstance(kw, list) else [kw],
        }

    return jsonify({
        "success": True,
        "domain": domain,
        "all_keywords": sorted(all_keywords),
        "sections": section_keywords,
        "count": len(rows),
    })
