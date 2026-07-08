"""FlashSloth — 账号管理路由：账号CRUD + 缓存 + 批量操作"""
from flashsloth.routes._app import app
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

import json
import os
from datetime import datetime

from flashsloth.core.database import get_db, DB_PATH
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.credential_crypto import decrypt_config, encrypt_config
from flashsloth.core.status_cache import get_status, set_status, get_all_cached, get_cache_stats
from flashsloth.core.status_detector import detect_platform, PLATFORM_DETECTORS
from flashsloth.core.deployer import list_deployers

SENSITIVE_FIELDS = {"password", "cookie", "app_secret", "api_key", "token", "access_token", "refresh_token"}
MASKED_VALUE = "••••••••"


# ─── 平台账号管理 ──────────────────────────────
@app.route("/accounts")
@login_required
def accounts():
   conn = get_db()
   accounts = conn.execute(
       "SELECT * FROM platform_accounts WHERE user_id=? ORDER BY platform, created_at",
       (current_user.id,)
   ).fetchall()
   # 加载部署配置和日志（内联到 #deploy 区块）
   deploy_configs = conn.execute(
       "SELECT * FROM deployer_configs WHERE user_id=? ORDER BY created_at DESC",
       (current_user.id,)
   ).fetchall()
   deploy_logs = conn.execute(
       "SELECT * FROM deploy_log ORDER BY created_at DESC LIMIT 20"
   ).fetchall()
   conn.close()
   platforms = list_publishers()
   # 按平台分组
   grouped = {}
   for a in accounts:
       grouped.setdefault(a["platform"], []).append(dict(a))

   # 加载缓存的登录状态
   cached_statuses = get_all_cached()
   deployer_list = list_deployers()

   return render_template("accounts.html",
                        grouped=grouped,
                        platforms=platforms,
                        cached_statuses=cached_statuses,
                        deployers=deployer_list,
                        configs=deploy_configs,
                        logs=deploy_logs)


@app.route("/api/accounts/config/<int:aid>")
@login_required
def api_accounts_config(aid):
    """返回指定账号的完整配置（含平台信息）"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    conn.close()
    if not acct:
        return jsonify({"success": False, "error": "账号不存在"})
    cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
    decrypt_config(cfg)  # 解密敏感字段
    cfg["_platform"] = acct["platform"]
    cfg["_accountName"] = acct["account_name"]
    # 脱敏敏感字段
    masked = {}
    for k, v in cfg.items():
        if k.startswith("_"):
            masked[k] = v
        elif k.lower() in SENSITIVE_FIELDS and v:
            masked[k] = MASKED_VALUE
        else:
            masked[k] = v
    return jsonify({"success": True, "config": masked})


@app.route("/accounts/add", methods=["POST"])
@login_required
def add_account():
   platform = request.form.get("platform", "")
   name = request.form.get("account_name", "")
   if not platform or not name:
       if not name:
           # 自动生成不重名默认别名
           conn = get_db()
           existing = conn.execute(
               "SELECT account_name FROM platform_accounts WHERE user_id=? AND platform=?",
               (current_user.id, platform)
           ).fetchall()
           conn.close()
           existing_names = {r["account_name"] for r in existing}
           base = platform
           idx = 1
           while f"{base}{idx:02d}" in existing_names:
               idx += 1
           name = f"{base}{idx:02d}"
       if not platform:
           flash("请选择平台", "error")
           return redirect(url_for("accounts"))
   # 收集该平台的所有配置字段
   cfg = {}
   for key in request.form:
       if key.startswith(f"cfg_"):
           cfg[key[4:]] = request.form[key]

   # 检查是否需要更新已有账号
   edit_id = request.form.get("edit_id", "")
   edit_id_int = int(edit_id) if edit_id and edit_id.isdigit() else 0

   conn = get_db()
   if edit_id_int:
       # 更新已有账号：加载原配置，掩码字段保留原值
       existing = conn.execute(
           "SELECT id, config_json FROM platform_accounts WHERE id=? AND user_id=?",
           (edit_id_int, current_user.id)
       ).fetchone()
       if existing:
           orig_cfg = json.loads(existing["config_json"]) if existing["config_json"] else {}
           decrypt_config(orig_cfg)  # 解密原配置
           for k, v in cfg.items():
               if v == MASKED_VALUE and k in orig_cfg:
                   cfg[k] = orig_cfg[k]  # 保留原值
           conn.execute(
               "UPDATE platform_accounts SET account_name=?, config_json=?, is_active=1 WHERE id=?",
               (name, json.dumps(encrypt_config(cfg)), edit_id_int),
           )
           conn.commit()
           conn.close()
           flash(f"{platform} 账号已更新", "success")
           return redirect(url_for("accounts"))
   conn.execute(
       "INSERT INTO platform_accounts (user_id, platform, account_name, config_json) VALUES (?, ?, ?, ?)",
       (current_user.id, platform, name, json.dumps(encrypt_config(cfg))),
   )
   conn.commit()
   conn.close()
   flash(f"{platform} 账号已添加", "success")
   return redirect(url_for("accounts"))


@app.route("/accounts/edit/<int:aid>", methods=["GET", "POST"])
@login_required
def edit_account(aid):
   """重定向到账号管理页，由前端模态框处理编辑"""
   return redirect(url_for("accounts"))


@app.route("/accounts/delete/<int:aid>")
@login_required
def delete_account(aid):
   conn = get_db()
   conn.execute("DELETE FROM platform_accounts WHERE id=? AND user_id=?", (aid, current_user.id))
   conn.commit()
   conn.close()
   flash("账号已删除", "success")
   return redirect(url_for("accounts"))


@app.route("/api/accounts/<int:aid>/toggle", methods=["POST"])
@login_required
def api_account_toggle(aid):
   """切换账号启用/禁用状态"""
   conn = get_db()
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
       (aid, current_user.id)
   ).fetchone()
   if not acct:
       conn.close()
       return jsonify({"success": False, "error": "账号不存在"})
   new_status = 0 if acct["is_active"] else 1
   conn.execute(
       "UPDATE platform_accounts SET is_active=? WHERE id=?",
       (new_status, aid)
   )
   conn.commit()
   conn.close()
   return jsonify({"success": True, "is_active": bool(new_status)})


# ─── 批量操作 API ────────────────────────────────
@app.route("/api/accounts/batch/toggle", methods=["POST"])
@login_required
def api_accounts_batch_toggle():
    """批量启用/禁用账号"""
    data = request.get_json() or {}
    ids = data.get("ids", [])
    enable = data.get("enable", True)
    if not ids or not isinstance(ids, list):
        return jsonify({"success": False, "error": "请选择至少一个账号"})
    conn = get_db()
    placeholders = ",".join("?" for _ in ids)
    params = [1 if enable else 0] + ids + [current_user.id]
    conn.execute(
        f"UPDATE platform_accounts SET is_active=? WHERE id IN ({placeholders}) AND user_id=?",
        params
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"已{'启用' if enable else '禁用'} {len(ids)} 个账号"})


@app.route("/api/accounts/batch/delete", methods=["POST"])
@login_required
def api_accounts_batch_delete():
    """批量删除账号"""
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids or not isinstance(ids, list):
        return jsonify({"success": False, "error": "请选择至少一个账号"})
    conn = get_db()
    placeholders = ",".join("?" for _ in ids)
    params = ids + [current_user.id]
    conn.execute(
        f"DELETE FROM platform_accounts WHERE id IN ({placeholders}) AND user_id=?",
        params
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"已删除 {len(ids)} 个账号"})


def _save_cookie_to_account(aid: int, cookie_str: str):
    """保存 Cookie 到账号配置（加密后存储）"""
    conn = get_db()
    acct = conn.execute(
        "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
        (aid, current_user.id)
    ).fetchone()
    if acct:
        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        cfg["cookie"] = cookie_str
        encrypt_config(cfg)  # 🔐 加密后再存储
        conn.execute(
            "UPDATE platform_accounts SET config_json=? WHERE id=?",
            (json.dumps(cfg), aid)
        )
        conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════
# 状态检测缓存 API
# ═══════════════════════════════════════════════════

@app.route("/api/accounts/cache/stats")
@login_required
def api_cache_stats():
    """返回缓存统计信息"""
    return jsonify({
        "success": True,
        "stats": get_cache_stats()
    })


@app.route("/api/accounts/cache/flush", methods=["POST"])
@login_required
def api_cache_flush():
    """清除所有状态缓存"""
    # 清除数据库中的 last_status_check
    conn = get_db()
    conn.execute("UPDATE platform_accounts SET status='', last_status_check='' WHERE user_id=?", (current_user.id,))
    conn.commit()
    conn.close()
    # 清除缓存文件（重启进程会让内存缓存失效）
    cache_db = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "status_cache.db")
    try:
        if os.path.exists(cache_db):
            os.remove(cache_db)
    except Exception:
        pass
    return jsonify({"success": True, "message": "所有缓存已清除"})


@app.route("/api/accounts/batch/refresh", methods=["POST"])
@login_required
def api_accounts_batch_refresh():
    """批量后台刷新所有活跃账号的状态（异步）

    ⚠️ 铁律：API轻量检测只能用于快速判定"未登录"（重定向到登录页等明确信号）。
    API轻量检测的"已登录"结果不可信任——它对假Cookie/过期Cookie可能误报为已登录。
    批量刷新仅做"状态预检"，不会用Playwright验证。
    如需真实登录态确认，请使用"状态检测"按钮（Playwright全量验证）。
    """
    conn = get_db()
    accounts = conn.execute(
        "SELECT * FROM platform_accounts WHERE user_id=? AND is_active=1",
        (current_user.id,)
    ).fetchall()
    conn.close()

    if not accounts:
        return jsonify({"success": True, "message": "没有活跃账号", "refreshed": 0})

    from flashsloth.core.status_detector import PLATFORM_DETECTORS

    refreshed = 0
    api_passed = 0
    api_failed = 0
    skipped = 0
    errors = []
    for acct in accounts:
        acct = dict(acct)
        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        try:
            from flashsloth.core.credential_crypto import decrypt_config
            decrypt_config(cfg)
        except Exception:
            pass

        platform = acct["platform"]
        site_url = cfg.get("site_url", "")
        cookie = cfg.get("cookie", "")
        username = cfg.get("username", "")

        # 只对支持API轻量检测的平台做批量刷新
        if platform in PLATFORM_DETECTORS and cookie and site_url:
            try:
                api_result = detect_platform(platform, site_url, cookie, username)
                # ⚠️ 铁律：API轻量检测只能信任"未登录"结果
                # "已登录"结果必须经过Playwright才能确认
                # 这里只缓存API检测结果，不标记为已登录
                if api_result.get("logged_in") == False:
                    # API明确检测到未登录（重定向到登录页等）→ 可信任
                    cache_data = {
                        "logged_in": False,
                        "username": "",
                        "display_name": "",
                        "points": 0,
                        "level": "",
                        "status": "❌ Cookie已失效（API轻量检测）",
                        "method": "api_lightweight",
                        "verified_at": datetime.now().isoformat(),
                        "error": api_result.get("error", "Cookie失效"),
                    }
                    set_status(acct["id"], cache_data)
                    api_failed += 1
                else:
                    # API检测通过 或 无明确判定
                    # → 缓存为"待确认"状态，提示用户点击"状态检测"按钮做Playwright验证
                    cache_data = {
                        "logged_in": None,  # null = 未确认
                        "username": api_result.get("username", ""),
                        "display_name": api_result.get("display_name", ""),
                        "points": api_result.get("points", 0),
                        "level": api_result.get("level", ""),
                        "status": "⏳ 待确认（API轻量检测通过，需要Playwright确认）",
                        "method": "api_lightweight",
                        "verified_at": datetime.now().isoformat(),
                    }
                    set_status(acct["id"], cache_data)
                    api_passed += 1
                refreshed += 1
            except Exception as e:
                errors.append(f"{acct['account_name']}: {str(e)[:80]}")
                skipped += 1
        else:
            # 不支持API轻量的平台，跳过
            skipped += 1

    return jsonify({
        "success": True,
        "refreshed": refreshed,
        "total": len(accounts),
        "api_passed": api_passed,
        "api_failed": api_failed,
        "skipped": skipped,
        "errors": errors[:5],
        "message": f"已刷新 {refreshed}/{len(accounts)} 个账号（API通过:{api_passed} API失效:{api_failed} 跳过:{skipped}）"
    })


@app.route("/api/accounts/test-connection", methods=["POST"])
@login_required
def api_test_connection():
    """测试账号连接 — 在保存前验证凭证有效性"""
    try:
        data = request.get_json(silent=True) or {}
        platform = data.get("platform", "")
        if not platform:
            # 尝试从 form-data 读取
            platform = request.form.get("platform", "")
        if not platform:
            return jsonify({"success": False, "error": "缺少平台名"})
        # 从 config 嵌套字段或 cfg_ 前缀字段读取
        config = {}
        nested_config = data.get("config", {})
        if isinstance(nested_config, dict):
            config.update(nested_config)
        # 也检查顶层 cfg_ 前缀字段
        for k, v in data.items():
            if k.startswith("cfg_"):
                config[k[4:]] = v
        # 也检查 form-data 中的 cfg_ 前缀字段
        for k, v in request.form.items():
            if k.startswith("cfg_"):
                config[k[4:]] = v
        # 尝试使用 publisher 的 test_connection
        from flashsloth.core.publisher import _registry as _publisher_registry
        cls = _publisher_registry.get(platform)
        result_data = {}
        if cls and hasattr(cls, 'test_connection') and callable(cls.test_connection):
            try:
                pub = cls(config)
                test_result = pub.test_connection()
                # ⚠️ 统一为 flat 格式（与 test_account() 返回格式一致）
                # discuz publisher 返回 {"success": True, "status": "已登录 — ...", ...}
                # 而前端 testConnectionAdd() 需要 data.logged_in / data.username / data.status
                result_data = {
                    "success": test_result.get("success", False),
                    "logged_in": test_result.get("success", False)
                        and ("已登录" in test_result.get("status", "") or test_result.get("status", "").startswith("✅")),
                    "status": test_result.get("status", "⏳ 未知"),
                    "username": test_result.get("username", "") or test_result.get("display_name", ""),
                    "platform": platform,
                    "error": test_result.get("error", ""),
                }
                return jsonify(result_data)
            except Exception as e:
                return jsonify({"success": False, "error": f"连接测试失败: {str(e)[:200]}"})
        # 降级：Cookie + site_url 进行 Playwright 验证（使用独立子进程，避免WSGI线程问题）
        cookie = config.get("cookie", data.get("cookie", ""))
        site_url = config.get("site_url", data.get("site_url", ""))
        username = config.get("username", data.get("username", ""))
        if cookie and site_url:
            # 使用子进程运行 Playwright 验证，传参通过 stdin JSON
            import subprocess as _sp, os as _os, sys as _sys
            _pw_env = _os.environ.copy()
            _pw_env["PYTHONPATH"] = f"{_os.path.expanduser('~/.hermes')}:{_os.path.expanduser('~/.hermes/flashsloth')}"
            _pw_script = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))), "scripts", "playwright_verify_raw.py")
            if _os.path.exists(_pw_script):
                try:
                    _input_json = json.dumps({
                        "cookie": cookie, "site_url": site_url,
                        "username": username, "platform": platform
                    }, ensure_ascii=False)
                    _pw_proc = _sp.run(
                        [_os.path.expanduser("~/.hermes/flashsloth/venv/bin/python3"), _pw_script],
                        capture_output=True, text=True, timeout=45, env=_pw_env,
                        input=_input_json,
                    )
                    if _pw_proc.returncode == 0 and _pw_proc.stdout.strip():
                        pw_result = json.loads(_pw_proc.stdout)
                        # playwright_verify_raw.py 已经返回 flat 格式（含 logged_in / username / status）
                        return jsonify(pw_result)
                except Exception as e:
                    pass  # Playwright 降级失败，兜底返回
            return jsonify({"success": False, "error": "无有效凭证可测试（需要 Cookie 或 账号密码）"})
        return jsonify({"success": False, "error": "需要配置站点 URL 和 Cookie 才能测试连接"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:200]})
