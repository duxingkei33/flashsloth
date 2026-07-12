"""FlashSloth — 工作台（统一内容管理页面）

从上到下 = 工作流顺序：
1️⃣ Provider 选择 → 文章列表
2️⃣ 流水线流程（采集→编译→预览→草稿→发布）
3️⃣ 内容日志（发布记录+采集记录）
"""
from flashsloth.routes._app import app

import json
import time
from datetime import datetime
from flask import (render_template, request, jsonify)
from flask_login import login_required, current_user

from flashsloth.core.database import get_db
from flashsloth.core.pipeline import (
    Pipeline, ContentObject, CONTENT_TYPES,
    create_pipeline,
)
from flashsloth.core.provider import (
    get_provider, list_providers, get_provider_names,
)

# 导入 Provider 插件（触发 @register_provider 装饰器）
import flashsloth.plugins.provider_markdown  # noqa: F401
import flashsloth.plugins.provider_notion    # noqa: F401
import flashsloth.plugins.provider_taobao    # noqa: F401


# 内存任务记录
_workspace_runs = []
_max_runs = 50


# ════════════════════════════════════════════════
# 页面
# ════════════════════════════════════════════════

@app.route("/workspace")
@login_required
def workspace_page():
    """工作台主页"""
    providers = list_providers()
    return render_template("workspace.html",
                         content_types=CONTENT_TYPES,
                         providers=providers)


@app.route("/pipeline")
@login_required
def pipeline_redirect():
    """向后兼容：/pipeline → 重定向到 /workspace"""
    from flask import redirect, url_for
    return redirect(url_for("workspace_page"))


# ════════════════════════════════════════════════
# Provider API
# ════════════════════════════════════════════════

@app.route("/api/workspace/providers")
@login_required
def api_workspace_providers():
    """列出所有可用的 Provider"""
    providers = list_providers()

    # 读取用户保存的 provider 配置
    conn = get_db()
    pconfig = conn.execute(
        "SELECT * FROM provider_config WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (current_user.id,)
    ).fetchone()
    conn.close()

    current_provider = None
    if pconfig:
        cfg = dict(pconfig)
        current_provider = {
            "type": cfg.get("provider_type", ""),
            "config_json": json.loads(cfg["config_json"]) if cfg.get("config_json") else {},
        }
    return jsonify({
        "success": True,
        "providers": providers,
        "current": current_provider,
    })


@app.route("/api/workspace/provider/<name>/items")
@login_required
def api_workspace_provider_items(name: str):
    """获取指定 Provider 的内容列表"""
    try:
        # 读取用户配置
        conn = get_db()
        pconfig = conn.execute(
            "SELECT * FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
            (current_user.id, name)
        ).fetchone()
        if not pconfig:
            # 试试不加 provider_type 过滤
            pconfig = conn.execute(
                "SELECT * FROM provider_config WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (current_user.id,)
            ).fetchone()
        conn.close()

        cfg = {}
        if pconfig:
            pc = dict(pconfig)
            if pc.get("config_json"):
                cfg = json.loads(pc["config_json"])

        provider = get_provider(name, cfg)
        items = provider.list_items()
        return jsonify({
            "success": True,
            "items": [i.__dict__ for i in items],
            "provider": provider.to_dict(),
        })
    except KeyError as e:
        return jsonify({"success": False, "error": str(e)})
    except Exception as e:
        return jsonify({"success": False, "error": f"加载失败: {e}"})


@app.route("/api/workspace/provider/<name>/item/<item_id>")
@login_required
def api_workspace_provider_item(name: str, item_id: str):
    """获取指定 Provider 的单个内容详情"""
    try:
        conn = get_db()
        pconfig = conn.execute(
            "SELECT * FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
            (current_user.id, name)
        ).fetchone()
        if not pconfig:
            pconfig = conn.execute(
                "SELECT * FROM provider_config WHERE user_id=? ORDER BY id DESC LIMIT 1",
                (current_user.id,)
            ).fetchone()
        conn.close()

        cfg = {}
        if pconfig:
            pc = dict(pconfig)
            if pc.get("config_json"):
                cfg = json.loads(pc["config_json"])

        provider = get_provider(name, cfg)
        content = provider.get_item_content(item_id)
        item = provider.get_item(item_id)
        return jsonify({
            "success": True,
            "content": content,
            "item": item.__dict__ if item else None,
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"加载失败: {e}"})


@app.route("/api/workspace/provider/<name>/config", methods=["GET", "POST"])
@login_required
def api_workspace_provider_config(name: str):
    """获取或保存指定 Provider 的配置"""
    if request.method == "GET":
        conn = get_db()
        pconfig = conn.execute(
            "SELECT * FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
            (current_user.id, name)
        ).fetchone()
        conn.close()
        cfg = {}
        if pconfig:
            pc = dict(pconfig)
            if pc.get("config_json"):
                cfg = json.loads(pc["config_json"])
        return jsonify({"success": True, "config": cfg})

    # POST — 保存配置
    data = request.get_json(force=True, silent=True) or {}
    cfg = data.get("config", {})
    if not isinstance(cfg, dict):
        return jsonify({"success": False, "error": "config 必须为 JSON 对象"})

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
        (current_user.id, name)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE provider_config SET config_json=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(cfg), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO provider_config (user_id, provider_type, config_json) VALUES (?, ?, ?)",
            (current_user.id, name, json.dumps(cfg)),
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": f"Provider '{name}' 配置已保存"})


# ════════════════════════════════════════════════
# 日志 API
# ════════════════════════════════════════════════

@app.route("/api/workspace/logs/publish")
@login_required
def api_workspace_publish_logs():
    """获取最近发布记录"""
    try:
        conn = get_db()
        logs = conn.execute(
            "SELECT pl.*, pa.account_name "
            "FROM publish_log pl "
            "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
            "ORDER BY pl.created_at DESC LIMIT 15"
        ).fetchall()
        conn.close()
        return jsonify({
            "success": True,
            "logs": [dict(l) for l in logs],
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "logs": []})


@app.route("/api/workspace/logs/collect")
@login_required
def api_workspace_collect_logs():
    """获取最近采集记录"""
    # 目前采集记录为空，后续可以从 pipeline 运行历史或其他来源填充
    try:
        runs = list(_workspace_runs)[:15]
        collect_logs = [
            {
                "id": r["id"],
                "title": r["title"],
                "success": r["success"],
                "created_at": r["created_at"],
                "type": r["type"],
            }
            for r in runs if any(s["stage"] == "collect" for s in r.get("stages", []))
        ]
        return jsonify({
            "success": True,
            "logs": collect_logs,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "logs": []})


# ════════════════════════════════════════════════
# 流水线 API（从 pipeline_ui.py 迁移）
# ════════════════════════════════════════════════

@app.route("/api/workspace/run", methods=["POST"])
@login_required
def api_workspace_run():
    """执行流水线"""
    data = request.get_json(force=True, silent=True) or {}
    content_type = data.get("content_type", "article")
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    tags = data.get("tags", "")
    until = data.get("until", "publish")

    if not title:
        return jsonify({"success": False, "error": "请输入标题"})

    obj = ContentObject(
        type=content_type,
        title=title,
        body=body,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        created_at=datetime.now().isoformat(),
    )

    pipe = create_pipeline(content_type)

    from flashsloth.core.pipeline import CollectHandler, CompileHandler, PreviewHandler, DraftHandler, PublishHandler

    pipe.set_handler("collect", CollectHandler())
    pipe.set_handler("compile", CompileHandler())
    pipe.set_handler("preview", PreviewHandler())
    pipe.set_handler("draft", DraftHandler())

    publish_platform = data.get("publish_platform", "")
    if until == "publish" and publish_platform:
        platform_publisher = _get_publisher_for(publish_platform, current_user.id)
        if platform_publisher:
            pipe.set_handler("publish", platform_publisher)

    stages = ["collect", "compile", "preview", "draft", "publish"]
    stage_results = []
    current = obj
    errors = []

    for stage in stages:
        handler = pipe.get_handler(stage)
        if not handler:
            stage_results.append({"stage": stage, "status": "skipped", "message": "未注册处理器"})
            continue

        try:
            current = pipe.run_stage(current, stage)
            stage_results.append({
                "stage": stage,
                "status": "passed",
                "message": f"{current.title} — {stage}完成",
            })
        except Exception as e:
            stage_results.append({
                "stage": stage,
                "status": "failed",
                "message": str(e),
            })
            errors.append(f"{stage}: {e}")
            break

        if stage == until:
            break

    run_id = f"p{int(time.time())}"
    record = {
        "id": run_id,
        "type": content_type,
        "title": title,
        "stages": stage_results,
        "success": len(errors) == 0,
        "errors": errors,
        "created_at": datetime.now().isoformat(),
    }
    _workspace_runs.insert(0, record)
    if len(_workspace_runs) > _max_runs:
        _workspace_runs.pop()

    return jsonify({
        "success": len(errors) == 0,
        "run_id": run_id,
        "stages": stage_results,
        "errors": errors,
        "result": current.to_dict() if len(errors) == 0 else None,
    })


@app.route("/api/workspace/history")
@login_required
def api_workspace_history():
    """流水线运行历史"""
    return jsonify({"runs": list(_workspace_runs)[:20]})


def _get_publisher_for(platform: str, user_id: int):
    """根据平台名获取发布器实例"""
    try:
        from flashsloth.core.publisher import get_publisher
        conn = get_db()
        acct = conn.execute(
            "SELECT * FROM platform_accounts WHERE platform=? AND user_id=? AND is_active=1",
            (platform, user_id)
        ).fetchone()
        conn.close()
        if not acct:
            return None
        cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
        pub = get_publisher(platform, cfg)
        return pub
    except Exception:
        return None
