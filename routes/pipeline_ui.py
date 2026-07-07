"""FlashSloth — 统一流水线管理页面"""
from flashsloth.routes._app import app

import json
import time
from datetime import datetime
from flask import (render_template, request, jsonify, redirect, url_for)
from flask_login import login_required, current_user

from flashsloth.core.database import get_db
from flashsloth.core.pipeline import (
    Pipeline, ContentObject, CONTENT_TYPES,
    create_pipeline,
)


# 内存任务记录（简单方案，后续可迁移到DB）
_pipeline_runs = []
_max_runs = 50


@app.route("/pipeline")
@login_required
def pipeline_page_redirect():
    """向后兼容：/pipeline → 重定向到 /workspace"""
    return redirect(url_for("workspace_page"))


@app.route("/api/pipeline/run", methods=["POST"])
@login_required
def api_pipeline_run():
    """执行流水线"""
    data = request.get_json(force=True, silent=True) or {}
    content_type = data.get("content_type", "article")
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    tags = data.get("tags", "")
    until = data.get("until", "publish")  # 跑到哪个阶段

    if not title:
        return jsonify({"success": False, "error": "请输入标题"})

    # 创建内容对象
    obj = ContentObject(
        type=content_type,
        title=title,
        body=body,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        created_at=datetime.now().isoformat(),
    )

    pipe = create_pipeline(content_type)

    # 注册基础处理器
    from flashsloth.core.pipeline import CollectHandler, CompileHandler, PreviewHandler, DraftHandler, PublishHandler

    pipe.set_handler("collect", CollectHandler())
    pipe.set_handler("compile", CompileHandler())
    pipe.set_handler("preview", PreviewHandler())
    pipe.set_handler("draft", DraftHandler())

    # 有发布目标才注册
    publish_platform = data.get("publish_platform", "")
    if until == "publish" and publish_platform:
        platform_publisher = _get_publisher_for(publish_platform, current_user.id)
        if platform_publisher:
            pipe.set_handler("publish", platform_publisher)

    # 按阶段依次执行，记录每步结果
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
            break  # 出错了停止

        if stage == until:
            break

    # 记录运行历史
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
    _pipeline_runs.insert(0, record)
    if len(_pipeline_runs) > _max_runs:
        _pipeline_runs.pop()

    return jsonify({
        "success": len(errors) == 0,
        "run_id": run_id,
        "stages": stage_results,
        "errors": errors,
        "result": current.to_dict() if len(errors) == 0 else None,
    })


@app.route("/api/pipeline/history")
@login_required
def api_pipeline_history():
    """流水线运行历史"""
    return jsonify({"runs": list(_pipeline_runs)[:20]})


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
