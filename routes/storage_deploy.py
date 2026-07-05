"""FlashSloth 存储管理 + 部署配置路由模块"""
from flashsloth.routes._app import app

from flask import render_template, request, redirect, url_for, flash, jsonify
import json, os

from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.storage import get_storage, list_storages
from flashsloth.core.deployer import get_deployer, list_deployers

STORAGE_DB_TYPE = "storage_config"

def _get_active_storage():
   """获取当前用户配置的存储后端"""
   conn = get_db()
   row = conn.execute(
       "SELECT * FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
       (current_user.id, STORAGE_DB_TYPE),
   ).fetchone()
   conn.close()

   if not row:
       return None

   cfg = json.loads(row["config_json"]) if row["config_json"] else {}
   backend = cfg.pop("backend", "local")
   try:
       return get_storage(backend, cfg)
   except Exception:
       return None

@app.route("/storage/settings")
@login_required
def storage_settings():
   """存储设置页面"""
   conn = get_db()
   row = conn.execute(
       "SELECT * FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
       (current_user.id, STORAGE_DB_TYPE),
   ).fetchone()
   conn.close()

   current_cfg = json.loads(row["config_json"]) if row else {}
   storages = list_storages()
   return render_template("storage_settings.html",
                        storages=storages,
                        current=current_cfg,
                        enabled=bool(current_cfg.get("backend")))

@app.route("/api/storage/save", methods=["POST"])
@login_required
def storage_save():
   """保存存储配置"""
   backend = request.json.get("backend", "")
   config = request.json.get("config", {})

   conn = get_db()
   existing = conn.execute(
       "SELECT id FROM provider_config WHERE user_id=? AND provider_type=? ORDER BY id DESC LIMIT 1",
       (current_user.id, STORAGE_DB_TYPE),
   ).fetchone()

   payload = json.dumps({"backend": backend, **config})
   if existing:
       conn.execute(
           "UPDATE provider_config SET config_json=?, updated_at=datetime('now') WHERE id=?",
           (payload, existing["id"]),
       )
   else:
       conn.execute(
           "INSERT INTO provider_config (user_id, provider_type, config_json) VALUES (?, ?, ?)",
           (current_user.id, STORAGE_DB_TYPE, payload),
       )
   conn.commit()
   conn.close()
   return jsonify({"success": True, "message": "存储配置已保存"})

@app.route("/api/storage/test", methods=["POST"])
@login_required
def storage_test():
   """测试存储连接"""
   backend = request.json.get("backend", "local")
   config = request.json.get("config", {})
   try:
       storage = get_storage(backend, config)
       result = storage.test_connection()
       return jsonify(result)
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

@app.route("/api/storage/list", methods=["POST"])
@login_required
def storage_list():
   """列文件目录"""
   path = request.json.get("path", "/")
   try:
       storage = _get_active_storage()
       if not storage:
           return jsonify({"success": False, "error": "未配置存储"})
       items = storage.list(path)
       return jsonify({"success": True, "items": items, "path": path})
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

@app.route("/api/storage/upload", methods=["POST"])
@login_required
def storage_upload():
   """上传文件到存储"""
   if "file" not in request.files:
       return jsonify({"success": False, "error": "未选择文件"})

   file = request.files["file"]
   article_id = request.form.get("article_id", type=int)
   remote_path = request.form.get("path", "")

   try:
       storage = _get_active_storage()
       if not storage:
           return jsonify({"success": False, "error": "未配置存储"})

       file_data = file.read()
       filename = file.filename

       if remote_path:
           # 上传到指定路径
           result = storage.upload_bytes(file_data, remote_path)
       elif article_id:
           # 上传为文章附件
           result = storage.upload_article_attachment_bytes(file_data, article_id, filename)
       else:
           # 按类型自动归类
           cat = storage.ensure_category_dir("resource")
           remote = f"/resource/{filename}"
           result = storage.upload_bytes(file_data, storage.full_path(remote))

       return jsonify({
           "success": True,
           "path": result.get("path", ""),
           "size": result.get("size", 0),
           "url": storage.get_url(result.get("path", "")),
       })
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

@app.route("/api/storage/mkdir", methods=["POST"])
@login_required
def storage_mkdir():
   """创建目录"""
   path = request.json.get("path", "")
   if not path:
       return jsonify({"success": False, "error": "缺少路径"})
   try:
       storage = _get_active_storage()
       if not storage:
           return jsonify({"success": False, "error": "未配置存储"})
       storage.mkdir(storage.full_path(path))
       return jsonify({"success": True})
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

@app.route("/api/storage/delete", methods=["POST"])
@login_required
def storage_delete():
   """删除文件/目录"""
   path = request.json.get("path", "")
   if not path:
       return jsonify({"success": False, "error": "缺少路径"})
   try:
       storage = _get_active_storage()
       if not storage:
           return jsonify({"success": False, "error": "未配置存储"})
       storage.delete(storage.full_path(path))
       return jsonify({"success": True})
   except Exception as e:
       return jsonify({"success": False, "error": str(e)})

# ─── 部署器 ──────────────────────────────────────

@app.route("/deployers")
@login_required
def deployers_page():
   """部署配置管理页"""
   conn = get_db()
   configs = conn.execute(
       "SELECT * FROM deployer_configs WHERE user_id=? ORDER BY created_at DESC",
       (current_user.id,)
   ).fetchall()
   logs = conn.execute(
       "SELECT * FROM deploy_log ORDER BY created_at DESC LIMIT 20"
   ).fetchall()
   conn.close()

   deployer_list = list_deployers()
   return render_template("deployers.html",
                        deployers=deployer_list,
                        configs=configs,
                        logs=logs)

@app.route("/deployers/add", methods=["POST"])
@login_required
def deployer_add():
   """添加部署配置"""
   deployer_name = request.form.get("deployer_name", "")
   display_name = request.form.get("display_name", "")
   if not deployer_name:
       flash("请选择部署器类型", "error")
       return redirect(url_for("storage.deployers_page"))

   # 收集配置
   dl = list_deployers()
   cfg = {}
   for d in dl:
       if d["name"] == deployer_name:
           display_name = display_name or d["display_name"]
           for field in d["config_fields"]:
               val = request.form.get(f"cfg_{field['key']}", "")
               if val:
                   cfg[field["key"]] = val
           break

   conn = get_db()
   conn.execute(
       "INSERT INTO deployer_configs (user_id, deployer_name, display_name, config_json) VALUES (?, ?, ?, ?)",
       (current_user.id, deployer_name, display_name, json.dumps(cfg))
   )
   conn.commit()
   conn.close()
   flash(f"部署配置「{display_name}」已添加", "success")
   return redirect(url_for("storage.deployers_page"))

@app.route("/deployers/delete/<int:cid>")
@login_required
def deployer_delete(cid):
   """删除部署配置"""
   conn = get_db()
   conn.execute("DELETE FROM deployer_configs WHERE id=? AND user_id=?",
                (cid, current_user.id))
   conn.commit()
   conn.close()
   flash("部署配置已删除", "success")
   return redirect(url_for("storage.deployers_page"))

@app.route("/deployers/deploy/<int:cid>")
@login_required
def deployer_run(cid):
   """执行部署"""
   conn = get_db()
   row = conn.execute(
       "SELECT * FROM deployer_configs WHERE id=? AND user_id=?",
       (cid, current_user.id)
   ).fetchone()
   if not row:
       conn.close()
       flash("部署配置不存在", "error")
       return redirect(url_for("storage.deployers_page"))

   cfg = json.loads(row["config_json"]) if row["config_json"] else {}
   try:
       deployer = get_deployer(row["deployer_name"], cfg)
       result = deployer.deploy()
       conn.execute(
           "INSERT INTO deploy_log (config_id, deployer_name, success, url, error, message) VALUES (?, ?, ?, ?, ?, ?)",
           (cid, row["deployer_name"],
            1 if result.get("success") else 0,
            result.get("url", ""),
            result.get("error", ""),
            result.get("message", ""))
       )
       conn.commit()

       if result.get("success"):
           msg = result.get("message", "部署成功")
           flash(f"✅ {msg}", "success")
           # 更新所有 pending 的发布记录为 deployed
           conn.execute(
               "UPDATE publish_log SET deploy_status='deployed', updated_at=datetime('now') "
               "WHERE deploy_status='pending' OR deploy_status IS NULL"
           )
           conn.commit()
           conn.close()
           # GitHub Pages 部署延迟提示
           if row["deployer_name"] == "github_pages":
               flash("⏳ GitHub Pages 需要 1-2 分钟刷新，请稍后访问站点确认", "info")
       else:
           flash(f"❌ 部署失败: {result.get('error', '未知错误')}", "error")
           conn.close()
   except Exception as e:
       conn.execute(
           "INSERT INTO deploy_log (config_id, deployer_name, success, error) VALUES (?, ?, 0, ?)",
           (cid, row["deployer_name"], str(e))
       )
       conn.commit()
       conn.close()
       flash(f"❌ 部署异常: {e}", "error")

   return redirect(url_for("storage.deployers_page"))

@app.route("/deployers/test/<int:cid>")
@login_required
def deployer_test(cid):
   """测试部署配置连接"""
   conn = get_db()
   row = conn.execute(
       "SELECT * FROM deployer_configs WHERE id=? AND user_id=?",
       (cid, current_user.id)
   ).fetchone()
   conn.close()
   if not row:
       flash("部署配置不存在", "error")
       return redirect(url_for("storage.deployers_page"))

   cfg = json.loads(row["config_json"]) if row["config_json"] else {}
   try:
       deployer = get_deployer(row["deployer_name"], cfg)
       result = deployer.test_connection()
       if result.get("success"):
           flash(f"✅ 连接正常: {result.get('status', '')}", "success")
       else:
           flash(f"❌ 连接失败: {result.get('error', '')}", "error")
   except Exception as e:
       flash(f"❌ 测试异常: {e}", "error")

   return redirect(url_for("storage.deployers_page"))

