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
   """部署配置管理页（增强版：含站点配置）"""
   conn = get_db()
   configs = conn.execute(
       "SELECT * FROM deployer_configs WHERE user_id=? ORDER BY created_at DESC",
       (current_user.id,)
   ).fetchall()
   logs = conn.execute(
       "SELECT * FROM deploy_log ORDER BY created_at DESC LIMIT 20"
   ).fetchall()
   sc = conn.execute(
       "SELECT * FROM site_configs WHERE user_id=? ORDER BY id DESC LIMIT 1",
       (current_user.id,)
   ).fetchone()
   conn.close()

   deployer_list = list_deployers()
   return render_template("deployers.html",
                        deployers=deployer_list,
                        configs=configs,
                        logs=logs,
                        site_config=dict(sc) if sc else None)

@app.route("/deployers/add", methods=["POST"])
@login_required
def deployer_add():
   """添加部署配置"""
   deployer_name = request.form.get("deployer_name", "")
   display_name = request.form.get("display_name", "")
   if not deployer_name:
       flash("请选择部署器类型", "error")
       return redirect("/accounts#deploy")

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
   return redirect("/accounts#deploy")

@app.route("/deployers/delete/<int:cid>")
@login_required
def deployer_delete(cid):
   conn = get_db()
   conn.execute("DELETE FROM deployer_configs WHERE id=? AND user_id=?",
                (cid, current_user.id))
   conn.commit()
   conn.close()
   flash("部署配置已删除", "success")
   return redirect("/accounts#deploy")

@app.route("/deployers/deploy/<int:cid>")
@login_required
def deployer_run(cid):
   conn = get_db()
   row = conn.execute(
       "SELECT * FROM deployer_configs WHERE id=? AND user_id=?",
       (cid, current_user.id)
   ).fetchone()
   if not row:
       conn.close()
       flash("部署配置不存在", "error")
       return redirect("/accounts#deploy")

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
           conn.execute(
               "UPDATE publish_log SET deploy_status='deployed', updated_at=datetime('now') "
               "WHERE deploy_status='pending' OR deploy_status IS NULL"
           )
           conn.commit()
           conn.close()
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

   return redirect("/accounts#deploy")

@app.route("/deployers/test/<int:cid>")
@login_required
def deployer_test(cid):
   conn = get_db()
   row = conn.execute(
       "SELECT * FROM deployer_configs WHERE id=? AND user_id=?",
       (cid, current_user.id)
   ).fetchone()
   conn.close()
   if not row:
       flash("部署配置不存在", "error")
       return redirect("/accounts#deploy")

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

   return redirect("/accounts#deploy")



# --- Site Configs API (博客平台/评论系统/插件) ---

BLOG_PLATFORMS = [
    {"id": "github_pages", "name": "GitHub Pages", "icon": "🐙", "desc": "GitHub 静态页面托管，支持自定义域名",
     "config_file": "gh-pages 分支", "recommended_comments": ["giscus", "utterances"]},
    {"id": "hexo", "name": "Hexo", "icon": "📝", "desc": "基于 Node.js 的静态博客框架，速度快、主题丰富",
     "config_file": "_config.yml", "recommended_comments": ["giscus", "utterances"]},
    {"id": "jekyll", "name": "Jekyll", "icon": "💎", "desc": "Ruby 静态站点生成器，GitHub Pages 原生支持",
     "config_file": "_config.yml", "recommended_comments": ["giscus", "utterances"]},
    {"id": "hugo", "name": "Hugo", "icon": "⚡", "desc": "Go 语言静态站点生成器，构建速度极快",
     "config_file": "config.toml / hugo.toml", "recommended_comments": ["giscus", "utterances", "waline"]},
    {"id": "vuepress", "name": "VuePress", "icon": "💚", "desc": "Vue 驱动的静态网站生成器，适合技术文档",
     "config_file": "docs/.vuepress/config.js", "recommended_comments": ["giscus", "twikoo"]},
    {"id": "vitepress", "name": "VitePress", "icon": "⚡", "desc": "Vite + Vue 驱动的静态站点生成器，VuePress 继任者",
     "config_file": "docs/.vitepress/config.js", "recommended_comments": ["giscus", "twikoo"]},
    {"id": "astro", "name": "Astro", "icon": "🚀", "desc": "全栈静态框架，支持 Islands 架构，性能卓越",
     "config_file": "astro.config.mjs", "recommended_comments": ["giscus", "utterances"]},
    {"id": "nextjs", "name": "Next.js", "icon": "▲", "desc": "React 全栈框架，支持 SSG/SSR，生态丰富",
     "config_file": "next.config.js", "recommended_comments": ["giscus", "utterances"]},
]

COMMENT_SYSTEMS = [
    {"id": "giscus", "name": "Giscus", "icon": "💬", "desc": "由 GitHub Discussions 驱动的评论系统（推荐）",
     "url": "https://giscus.app/zh-CN",
     "fields": [
         {"key": "repo", "label": "GitHub 仓库", "placeholder": "用户名/仓库名", "required": True},
         {"key": "repo_id", "label": "仓库 ID", "placeholder": "从 giscus.app 获取", "required": True},
         {"key": "category", "label": "分类名称", "placeholder": "如: Announcements", "required": True},
         {"key": "category_id", "label": "分类 ID", "placeholder": "从 giscus.app 获取", "required": True},
         {"key": "mapping", "label": "页面映射方式", "type": "select", "options": [{"value": "pathname", "label": "页面路径"}, {"value": "url", "label": "页面 URL"}, {"value": "title", "label": "页面标题"}, {"value": "og:title", "label": "OG 标题"}], "default": "pathname"},
     ]},
    {"id": "utterances", "name": "utterances", "icon": "🗣️", "desc": "基于 GitHub Issues 的轻量评论系统",
     "url": "https://utteranc.es/",
     "fields": [
         {"key": "repo", "label": "GitHub 仓库", "placeholder": "用户名/仓库名", "required": True},
         {"key": "issue_term", "label": "Issue 关联方式", "type": "select", "options": [{"value": "pathname", "label": "页面路径"}, {"value": "url", "label": "URL"}, {"value": "title", "label": "标题"}, {"value": "og:title", "label": "OG 标题"}], "default": "pathname"},
     ]},
    {"id": "twikoo", "name": "Twikoo", "icon": "☁️", "desc": "基于腾讯云函数的评论系统",
     "url": "https://twikoo.js.org/",
     "fields": [
         {"key": "env_id", "label": "环境 ID", "placeholder": "腾讯云函数环境 ID", "required": True},
         {"key": "region", "label": "云函数地域", "placeholder": "ap-guangzhou", "default": "ap-guangzhou"},
     ]},
    {"id": "waline", "name": "Waline", "icon": "📦", "desc": "自部署评论系统，支持 LeanCloud 数据库",
     "url": "https://waline.js.org/",
     "fields": [
         {"key": "server_url", "label": "服务端 URL", "placeholder": "https://your-waline-api.example.com", "required": True},
         {"key": "locale", "label": "语言", "type": "select", "options": [{"value": "zh-CN", "label": "简体中文"}, {"value": "en", "label": "English"}, {"value": "zh-TW", "label": "繁體中文"}], "default": "zh-CN"},
     ]},
    {"id": "disqus", "name": "Disqus", "icon": "🔷", "desc": "通用评论平台，全球最大评论服务",
     "url": "https://disqus.com/",
     "fields": [
         {"key": "shortname", "label": "Shortname", "placeholder": "你的 Disqus shortname", "required": True},
     ]},
]

PLUGINS = [
    {"id": "baidu_analytics", "name": "百度统计", "icon": "📊", "desc": "站点访问统计，了解访客行为",
     "fields": [{"key": "track_id", "label": "统计 ID", "placeholder": "百度统计站点 ID", "required": True}]},
    {"id": "google_analytics", "name": "Google Analytics", "icon": "📈", "desc": "Google 站点分析，全球最多人使用",
     "fields": [{"key": "track_id", "label": "跟踪 ID", "placeholder": "G-XXXXXXXXXX", "required": True}]},
    {"id": "local_search", "name": "本地搜索", "icon": "🔍", "desc": "无需服务端的站内搜索",
     "fields": [{"key": "service_worker", "label": "Service Worker 路径", "placeholder": "/sw.js", "default": "/sw.js"}]},
    {"id": "algolia", "name": "Algolia 搜索", "icon": "🔎", "desc": "高性能全文搜索服务，需 API Key",
     "fields": [
         {"key": "app_id", "label": "App ID", "placeholder": "Algolia App ID", "required": True},
         {"key": "api_key", "label": "Search-Only API Key", "placeholder": "仅搜索权限的 Key", "required": True},
         {"key": "index_name", "label": "索引名称", "placeholder": "如: posts", "required": True},
     ]},
    {"id": "pwa", "name": "PWA / Service Worker", "icon": "📱", "desc": "离线支持 + 添加到主屏幕",
     "fields": [
         {"key": "sw_path", "label": "Service Worker 路径", "placeholder": "/sw.js", "default": "/sw.js"},
         {"key": "manifest_path", "label": "Manifest 路径", "placeholder": "/manifest.json", "default": "/manifest.json"},
     ]},
    {"id": "social_share", "name": "社交分享按钮", "icon": "🌐", "desc": "将文章分享到微信/微博/Twitter/Facebook",
     "fields": [{"key": "platforms", "label": "启用平台(逗号分隔)", "placeholder": "weibo,twitter,facebook,wechat", "default": "weibo,twitter"}]},
    {"id": "friend_links", "name": "友情链接", "icon": "🔗", "desc": "管理博客的友情链接",
     "fields": [{"key": "links_json", "label": "友链 JSON", "placeholder": '[{"name":"Example","url":"https://..."}]', "type": "textarea"}]},
    {"id": "email_subscribe", "name": "邮件订阅", "icon": "📧", "desc": "读者通过邮件订阅新文章通知",
     "fields": [
         {"key": "api_endpoint", "label": "订阅 API 端点", "placeholder": "https://your-api.com/subscribe", "required": True},
         {"key": "from_name", "label": "发件人名称", "placeholder": "博客名称", "default": "我的博客"},
     ]},
    {"id": "lazy_load", "name": "图片懒加载", "icon": "🖼️", "desc": "延迟加载图片，提升页面加载速度",
     "fields": [{"key": "loading_type", "label": "加载方式", "type": "select", "options": [{"value": "native", "label": "Native lazy (loading=lazy)"}, {"value": "lazysizes", "label": "lazysizes.js (更兼容)"}], "default": "native"}]},
    {"id": "image_optimize", "name": "图片优化", "icon": "🎨", "desc": "自动压缩/转码图片，支持 WebP 格式",
     "fields": [
         {"key": "quality", "label": "压缩质量", "placeholder": "80", "default": "80", "type": "number"},
         {"key": "webp", "label": "启用 WebP", "type": "select", "options": [{"value": "1", "label": "是"}, {"value": "0", "label": "否"}], "default": "1"},
     ]},
    {"id": "cdn", "name": "CDN 加速", "icon": "⚡", "desc": "静态资源 CDN 加速（jsDelivr/UNPKG）",
     "fields": [
         {"key": "provider", "label": "CDN 提供商", "type": "select", "options": [{"value": "jsdelivr", "label": "jsDelivr"}, {"value": "unpkg", "label": "UNPKG"}, {"value": "custom", "label": "自定义"}], "default": "jsdelivr"},
         {"key": "custom_url", "label": "自定义 CDN 地址", "placeholder": "仅自定义时填写", "default": ""},
     ]},
]

@app.route("/api/deploy/site-config", methods=["GET"])
@login_required
def api_get_site_config():
    """获取当前用户的站点全局配置"""
    conn = get_db()
    sc = conn.execute(
        "SELECT * FROM site_configs WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (current_user.id,)
    ).fetchone()
    conn.close()
    return jsonify({
        "success": True,
        "config": dict(sc) if sc else {
            "platform": "github_pages",
            "comment_system": "",
            "comment_config": "{}",
            "plugins_config": "{}",
            "extra_config": "{}",
        }
    })

@app.route("/api/deploy/site-config", methods=["POST"])
@login_required
def api_save_site_config():
    """保存站点全局配置（平台/评论/插件）"""
    data = request.get_json() or {}
    platform = data.get("platform", "github_pages")
    comment_system = data.get("comment_system", "")
    comment_config = json.dumps(data.get("comment_config", {}), ensure_ascii=False)
    plugins_config = json.dumps(data.get("plugins_config", {}), ensure_ascii=False)
    extra_config = json.dumps(data.get("extra_config", {}), ensure_ascii=False)
    deployer_id = data.get("deployer_id")

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM site_configs WHERE user_id=? ORDER BY id DESC LIMIT 1",
        (current_user.id,)
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE site_configs SET platform=?, comment_system=?, comment_config=?,
               plugins_config=?, extra_config=?, deployer_id=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (platform, comment_system, comment_config, plugins_config,
             extra_config, deployer_id, existing["id"])
        )
    else:
        conn.execute(
            """INSERT INTO site_configs (user_id, deployer_id, platform, comment_system,
               comment_config, plugins_config, extra_config)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (current_user.id, deployer_id, platform, comment_system,
             comment_config, plugins_config, extra_config)
        )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "站点配置已保存"})

@app.route("/api/deploy/platforms")
@login_required
def api_deploy_platforms():
    """获取博客平台列表"""
    return jsonify({"success": True, "platforms": BLOG_PLATFORMS})

@app.route("/api/deploy/comments")
@login_required
def api_deploy_comments():
    """获取评论系统列表"""
    return jsonify({"success": True, "systems": COMMENT_SYSTEMS})

@app.route("/api/deploy/plugins")
@login_required
def api_deploy_plugins():
    """获取插件列表"""
    return jsonify({"success": True, "plugins": PLUGINS})

# ─── Unified Account Deploy API (aliases) ────────────────────
@app.route("/api/accounts/deploy/site-config", methods=["GET"])
@login_required
def accounts_api_get_site_config():
    """Unified API: get site config (alias for /api/deploy/site-config)"""
    return api_get_site_config()

@app.route("/api/accounts/deploy/site-config", methods=["POST"])
@login_required
def accounts_api_save_site_config():
    """Unified API: save site config (alias for /api/deploy/site-config)"""
    return api_save_site_config()

@app.route("/api/accounts/deploy/platforms")
@login_required
def accounts_api_deploy_platforms():
    """Unified API: list blog platforms"""
    return api_deploy_platforms()

@app.route("/api/accounts/deploy/comments")
@login_required
def accounts_api_deploy_comments():
    """Unified API: list comment systems"""
    return api_deploy_comments()

@app.route("/api/accounts/deploy/plugins")
@login_required
def accounts_api_deploy_plugins():
    """Unified API: list site plugins"""
    return api_deploy_plugins()
