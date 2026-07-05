"""posts_bp — 文章管理 + 发布流程路由"""
from flashsloth.routes._app import app
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from flashsloth.core.database import get_db
from flashsloth.core.article import Article
from flashsloth.core.publisher import get_publisher, list_publishers
from flashsloth.core.deployer import get_deployer, list_deployers
import json, time, os, re, threading, datetime
from datetime import datetime

# ─── 文章 CRUD ─────────────────────────────────
@app.route("/post/new", methods=["GET", "POST"])
@login_required
def new_post():
   if request.method == "POST":
       conn = get_db()
       conn.execute(
           "INSERT INTO articles (user_id, title, body, summary, tags) VALUES (?, ?, ?, ?, ?)",
           (current_user.id,
            request.form.get("title", ""),
            request.form.get("body", ""),
            request.form.get("summary", ""),
            json.dumps([t.strip() for t in request.form.get("tags", "").split(",") if t.strip()])),
       )
       conn.commit()
       conn.close()
       flash("文章已保存", "success")
       return redirect(url_for("index"))
   return render_template("edit.html", post=None)

@app.route("/post/edit/<int:pid>", methods=["GET", "POST"])
@login_required
def edit_post(pid):
   conn = get_db()
   if request.method == "POST":
       conn.execute(
           "UPDATE articles SET title=?, body=?, summary=?, tags=?, updated_at=datetime('now') WHERE id=? AND user_id=?",
           (request.form.get("title", ""), request.form.get("body", ""),
            request.form.get("summary", ""),
            json.dumps([t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]),
            pid, current_user.id),
       )
       conn.commit()
       conn.close()
       flash("文章已更新", "success")
       return redirect(url_for("index"))

   post = conn.execute(
       "SELECT * FROM articles WHERE id=? AND user_id=?",
       (pid, current_user.id)
   ).fetchone()
   conn.close()
   if not post:
       flash("文章不存在", "error")
       return redirect(url_for("index"))
   return render_template("edit.html", post=post)

@app.route("/post/delete/<int:pid>")
@login_required
def delete_post(pid):
   conn = get_db()
   conn.execute("DELETE FROM articles WHERE id=? AND user_id=?", (pid, current_user.id))
   conn.commit()
   conn.close()
   flash("文章已删除", "success")
   return redirect(url_for("index"))

# ─── 发布 ───────────────────────────────────────
@app.route("/publish", methods=["POST"])
@login_required
def publish():
   """从文章列表选择发布：选择文章 + 选择平台账号"""
   article_id = request.form.get("article_id", type=int)
   account_ids = request.form.getlist("account_ids")

   if not article_id or not account_ids:
       flash("请选择文章和发布目标", "error")
       return redirect(url_for("index"))

   conn = get_db()
   post = conn.execute(
       "SELECT * FROM articles WHERE id=? AND user_id=?",
       (article_id, current_user.id)
   ).fetchone()
   if not post:
       flash("文章不存在", "error")
       conn.close()
       return redirect(url_for("index"))

   article = Article(
       title=post["title"],
       body=post["body"],
       summary=post["summary"],
       tags=json.loads(post["tags"]) if post["tags"] else [],
   )

   results = []
   for aid in account_ids:
       acct = conn.execute(
           "SELECT * FROM platform_accounts WHERE id=? AND user_id=?",
           (aid, current_user.id)
       ).fetchone()
       if not acct:
           continue

       cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
       # 检查是否有发布时选择的板块（Discuz 等论坛）
       forum_fid = request.form.get(f"forum_fid_{aid}")
       if forum_fid:
           cfg["fid"] = forum_fid

       # 读取发布模式
       mode = request.form.get(f"mode_{aid}", "publish")
       cfg["publish_mode"] = mode

       # 去重：检查是否已发布到该账号
       existing = conn.execute(
           "SELECT id FROM publish_log WHERE article_id=? AND account_id=? AND success=1",
           (article_id, aid)
       ).fetchone()
       if existing:
           results.append({"success": True, "error": "", "message": "already_published"})
           continue

       try:
           # 编译文章到该平台格式
           compiled_body = article.body
           compiled_title = article.title
           try:
               from core.compiler import Compiler
               comp = Compiler()
               comp_results = comp.compile(article, targets=[acct["platform"]])
               if acct["platform"] in comp_results:
                   cr = comp_results[acct["platform"]]
                   if cr.success:
                       compiled_body = cr.body
                       compiled_title = cr.title
           except Exception:
               pass  # 编译失败就用原始内容

           # 用编译后的内容创建文章
           compiled_article = Article(
               title=compiled_title,
               body=compiled_body,
               summary=article.summary,
               tags=article.tags,
           )

           publisher = get_publisher(acct["platform"], cfg)
           result = publisher.publish(compiled_article)
           publish_status = result.get("message", "published") if result["success"] else "failed"
           conn.execute(
               "INSERT INTO publish_log (article_id, account_id, platform, success, url, error, message, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (article_id, aid, acct["platform"],
                1 if result["success"] else 0,
                result.get("url", ""), result.get("error", ""),
                result.get("message", ""), publish_status),
           )
           results.append(result)
       except Exception as e:
           conn.execute(
               "INSERT INTO publish_log (article_id, account_id, platform, success, error) VALUES (?, ?, ?, 0, ?)",
               (article_id, aid, acct["platform"], str(e)),
           )
           results.append({"success": False, "error": str(e)})

   if any(r["success"] for r in results):
       conn.execute("UPDATE articles SET status='published', updated_at=datetime('now') WHERE id=?", (article_id,))

   conn.commit()

   # ── 自动部署：发布成功后自动触发所有活跃部署器 ──
   if any(r["success"] for r in results):
       deployers = conn.execute(
           "SELECT * FROM deployer_configs WHERE user_id=? AND is_active=1",
           (current_user.id,)
       ).fetchall()
       for dep in deployers:
           cfg = json.loads(dep["config_json"]) if dep["config_json"] else {}
           try:
               deployer = get_deployer(dep["deployer_name"], cfg)
               result = deployer.deploy()
               if result.get("success"):
                   conn.execute(
                       "UPDATE publish_log SET deploy_status='deployed' WHERE article_id=? AND (deploy_status IS NULL OR deploy_status='pending')",
                       (article_id,),
                   )
                   if dep["deployer_name"] == "github_pages":
                       flash("⏳ GitHub Pages 需要 1-2 分钟刷新，请稍后查看", "info")
           except Exception:
               pass  # 部署失败不阻塞发布结果
       conn.commit()

   conn.close()

   success_count = sum(1 for r in results if r["success"])
   already_published = sum(1 for r in results if r.get("message") == "already_published")
   pending_count = sum(1 for r in results if r.get("message") == "pending_review")
   parts = []
   if success_count:
       parts.append(f"{success_count} 成功")
   if already_published:
       parts.append(f"{already_published} 已发布跳过")
   if pending_count:
       parts.append(f"{pending_count} 待审核")
   failed = len(results) - success_count - already_published
   if failed:
       parts.append(f"{failed} 失败")
   flash(f"发布完成: {'; '.join(parts)}", "success" if success_count else "error")
   return redirect(url_for("index"))


# ─── 编译预览 ────────────────────────────────────
@app.route("/compile/<int:pid>")
@login_required
def compile_preview(pid):
    """编译文章并在各平台预览效果"""
    conn = get_db()
    post = conn.execute(
        "SELECT * FROM articles WHERE id=? AND user_id=?",
        (pid, current_user.id)
    ).fetchone()
    conn.close()

    if not post:
        flash("文章不存在", "error")
        return redirect(url_for("index"))

    try:
        from core.compiler import Compiler
    except ImportError:
        from flashsloth.core.compiler import Compiler

    article = Article(
        title=post["title"],
        body=post["body"],
        tags=json.loads(post["tags"]) if post["tags"] else [],
        summary=post["summary"],
    )

    compiler = Compiler()
    # 编译到所有支持的平台
    targets = None
    results = compiler.compile(article, targets=targets)

    return render_template("compile_preview.html",
                         results=results,
                         article_id=pid,
                         title=post["title"],
                         tags=", ".join(json.loads(post["tags"])) if post["tags"] else "")


@app.route("/api/compile/<int:pid>")
@login_required
def api_compile(pid):
    """编译 API — 返回 JSON 格式的编译结果"""
    conn = get_db()
    post = conn.execute(
        "SELECT * FROM articles WHERE id=? AND user_id=?",
        (pid, current_user.id)
    ).fetchone()
    conn.close()

    if not post:
        return jsonify({"success": False, "error": "文章不存在"})

    try:
        from core.compiler import Compiler
    except ImportError:
        from flashsloth.core.compiler import Compiler

    targets = request.args.getlist("targets") or None

    article = Article(
        title=post["title"],
        body=post["body"],
        tags=json.loads(post["tags"]) if post["tags"] else [],
        summary=post["summary"],
    )

    compiler = Compiler()
    results = compiler.compile(article, targets=targets)

    # 转为可序列化格式
    serialized = {}
    for platform, content in results.items():
        serialized[platform] = {
            "platform": content.platform,
            "display_name": content.display_name,
            "title": content.title,
            "body": content.body,
            "summary": content.summary,
            "tags": content.tags,
            "images": content.images,
            "image_warnings": content.image_warnings,
            "fields": content.fields,
            "warnings": content.warnings,
            "success": content.success,
            "error": content.error,
        }

    return jsonify({"success": True, "results": serialized})

# ─── 批量发布页面 ──────────────────────────────
@app.route("/publish/select/<int:pid>")
@login_required
def publish_select(pid):
   conn = get_db()
   post = conn.execute(
       "SELECT * FROM articles WHERE id=? AND user_id=?",
       (pid, current_user.id)
   ).fetchone()
   accounts = conn.execute(
       "SELECT * FROM platform_accounts WHERE user_id=? AND is_active=1",
       (current_user.id,)
   ).fetchall()
   # 获取该文章已发布的记录
   published = conn.execute(
       "SELECT pl.*, pa.account_name, pa.platform FROM publish_log pl "
       "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
       "WHERE pl.article_id=? AND pl.success=1 "
       "ORDER BY pl.created_at DESC",
       (pid,),
   ).fetchall()
   conn.close()

   if not post:
       flash("文章不存在", "error")
       return redirect(url_for("index"))

   return render_template("publish_select.html",
                        post=post, accounts=accounts,
                        published=[dict(p) for p in published])

# ─── 撤回 / 重新发布 ──────────────────────────
@app.route("/publish/retract/<int:log_id>")
@login_required
def publish_retract(log_id):
   """撤回已发布的文章"""
   conn = get_db()
   log = conn.execute(
       "SELECT pl.*, a.title, a.body, a.tags FROM publish_log pl "
       "LEFT JOIN articles a ON pl.article_id=a.id "
       "WHERE pl.id=? AND (a.user_id=? OR ?)",
       (log_id, current_user.id, current_user.is_admin)
   ).fetchone()
   if not log:
       conn.close()
       flash("发布记录不存在", "error")
       return redirect(url_for("index"))

   # 获取 publisher 并执行撤回
   acct = conn.execute(
       "SELECT * FROM platform_accounts WHERE id=?",
       (log["account_id"],)
   ).fetchone()
   conn.close()

   if not acct:
       flash("关联账号不存在", "error")
       return redirect(url_for("index"))

   cfg = json.loads(acct["config_json"]) if acct["config_json"] else {}
   try:
       publisher = get_publisher(acct["platform"], cfg)
       article = Article(
           title=log["title"] or "",
           body=log["body"] or "",
           tags=json.loads(log["tags"]) if log["tags"] else [],
       )
       log_dict = dict(log)
       result = publisher.retract(article, log_dict)

       if result.get("success"):
           # 更新发布日志状态（含部署状态）
           deploy_update = ", deploy_status='retracted'" if acct["platform"] in ("github_pages_blog",) else ""
           conn2 = get_db()
           conn2.execute(
               f"UPDATE publish_log SET status=?, retracted_at=datetime('now'){deploy_update} WHERE id=?",
               ("retracted", log_id),
           )
           # 同步更新文章状态为 draft
           if log.get("article_id"):
               conn2.execute(
                   "UPDATE articles SET status='draft', updated_at=datetime('now') WHERE id=?",
                   (log["article_id"],),
               )
           conn2.close()
           flash(f"✅ 撤回成功: {result.get('message', '')}", "success")
           # 如果是 GitHub Pages，自动部署（hugo rebuild + git push）
           if acct["platform"] == "github_pages_blog":
               try:
                   blog_dir = os.path.dirname(os.path.dirname(cfg.get("posts_dir", "")))
                   if blog_dir and os.path.isdir(blog_dir):
                       # 1. Hugo rebuild
                       import subprocess
                       hugo_bin = "/opt/data/bin/hugo"
                       if os.path.isfile(hugo_bin):
                           hugo_result = subprocess.run(
                               [hugo_bin], cwd=blog_dir,
                               capture_output=True, text=True, timeout=60
                           )
                           if hugo_result.returncode != 0:
                               flash(f"⚠️ Hugo构建失败: {hugo_result.stderr[:200]}", "warning")
                       # 2. Git commit + push (用deployer配置的repo_dir)
                       deploy_row = conn2.execute(
                           "SELECT config_json FROM deployer_configs WHERE deployer_name='github_pages' LIMIT 1"
                       ).fetchone()
                       if deploy_row:
                           dep_cfg = json.loads(deploy_row["config_json"])
                           repo_dir = dep_cfg.get("repo_dir", "")
                           token = dep_cfg.get("github_token", "")
                           username = dep_cfg.get("github_username", "")
                           if repo_dir and token and os.path.isdir(repo_dir):
                               auth_url = f"https://{username}:{token}@github.com/{username}/{username}.github.io.git"
                               cmds = [
                                   ["git", "-C", repo_dir, "add", "-A"],
                               ]
                               for cmd in cmds:
                                   subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                               ts = __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')
                               subprocess.run(
                                   ["git", "-C", repo_dir, "commit", "-m", f"retract: auto-sync @ {ts}"],
                                   capture_output=True, text=True, timeout=30
                               )
                               # 先保存原remote，临时换带token的
                               old_remote = subprocess.run(
                                   ["git", "-C", repo_dir, "remote", "get-url", "origin"],
                                   capture_output=True, text=True, timeout=10
                               ).stdout.strip()
                               subprocess.run(
                                   ["git", "-C", repo_dir, "remote", "set-url", "origin", auth_url],
                                   capture_output=True, text=True, timeout=10
                               )
                               push_result = subprocess.run(
                                   ["git", "-C", repo_dir, "push", "origin", dep_cfg.get("branch", "main")],
                                   capture_output=True, text=True, timeout=30
                               )
                               # 恢复remote
                               subprocess.run(
                                   ["git", "-C", repo_dir, "remote", "set-url", "origin", old_remote],
                                   capture_output=True, text=True, timeout=10
                               )
                               if push_result.returncode == 0:
                                   flash("✅ 撤回内容已自动部署到 GitHub Pages，1-2分钟生效", "success")
                               else:
                                   flash(f"⚠️ 推送失败: {push_result.stderr[:200]}", "warning")
               except Exception as e:
                   flash(f"⚠️ 自动部署异常: {e}", "warning")
       else:
           flash(f"❌ 撤回失败: {result.get('error', '未知错误')}", "error")
   except Exception as e:
       flash(f"❌ 撤回异常: {e}", "error")

   return redirect(url_for("posts.publish_manage"))

@app.route("/publish/re-publish/<int:log_id>")
@login_required
def publish_republish(log_id):
   """重新发布已撤回的文章"""
   conn = get_db()
   log = conn.execute(
       "SELECT * FROM publish_log WHERE id=?",
       (log_id,)
   ).fetchone()
   if not log:
       conn.close()
       flash("发布记录不存在", "error")
       return redirect(url_for("index"))

   # 重置发布日志状态
   conn.execute(
       "UPDATE publish_log SET status='published', retracted_at=NULL, created_at=datetime('now') WHERE id=?",
       (log_id,),
   )
   conn.commit()
   conn.close()

   flash("✅ 已标记为重新发布，请手动执行发布操作", "success")
   return redirect(url_for("posts.publish_manage"))

# ─── 发布管理 ──────────────────────────────────
@app.route("/publish/manage")
@login_required
def publish_manage():
   """发布管理页面 — 查看所有发布状态，支持撤回"""
   conn = get_db()

   # 所有发布记录（含撤回的）
   logs = conn.execute(
       "SELECT pl.*, pa.account_name, pa.platform as pa_platform, a.title as article_title "
       "FROM publish_log pl "
       "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
       "LEFT JOIN articles a ON pl.article_id=a.id "
       "WHERE a.user_id=? OR ? "
       "ORDER BY pl.created_at DESC LIMIT 50",
       (current_user.id, current_user.is_admin)
   ).fetchall()

   # 按文章分组统计
   articles_raw = conn.execute(
       "SELECT a.*, "
       "(SELECT COUNT(*) FROM publish_log pl WHERE pl.article_id=a.id AND pl.success=1 AND (pl.status='published' OR pl.status IS NULL)) as pub_count, "
       "(SELECT COUNT(*) FROM publish_log pl WHERE pl.article_id=a.id AND pl.status='retracted') as ret_count "
       "FROM articles a WHERE a.user_id=? ORDER BY a.updated_at DESC",
       (current_user.id,)
   ).fetchall()

   # 给每篇文章附上已发布的 URL 列表
   articles = []
   for a in articles_raw:
       a = dict(a)
       pub_urls = conn.execute(
           "SELECT pl.platform, pl.url, pa.account_name, pl.deploy_status FROM publish_log pl "
           "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
           "WHERE pl.article_id=? AND pl.success=1 AND (pl.status='published' OR pl.status IS NULL) "
           "ORDER BY pl.created_at DESC",
           (a['id'],)
       ).fetchall()
       a['published_urls'] = [dict(u) for u in pub_urls]
       articles.append(a)

   conn.close()

   return render_template("publish_manage.html",
                        logs=[dict(l) for l in logs],
                        articles=[dict(a) for a in articles])

# ─── 检查待审核帖子状态 ────────────────────────────
@app.route("/api/publish/check-pending")
@login_required
def api_check_pending():
   """检查所有待审核帖子的实际状态，更新 DB 并返回结果"""
   conn = get_db()

   pending_logs = conn.execute(
       "SELECT pl.*, pa.platform, pa.config_json, pa.account_name "
       "FROM publish_log pl "
       "LEFT JOIN platform_accounts pa ON pl.account_id=pa.id "
       "WHERE pl.status='pending_review' AND pl.success=1 "
       "AND (pa.user_id=? OR ?) "
       "ORDER BY pl.created_at DESC",
       (current_user.id, current_user.is_admin)
   ).fetchall()

   if not pending_logs:
       conn.close()
       return jsonify({"ok": True, "checked": 0, "updated": 0, "details": []})

   results = []
   updated_count = 0

   for log in pending_logs:
       log = dict(log)
       tid = None
       platform = log.get("platform", "")

       # 从 URL 提取帖子 ID
       if log.get("url"):
           # 支持 thread-N-1-1.html 和 tid=N 两种格式
           m = re.search(r'thread[=\\-/]?(\d+)|[?&]tid=(\d+)', log["url"])
           if m:
               tid = m.group(1) or m.group(2)
       if not tid and log.get("id"):
           tid = str(log["id"])

       result = {
           "log_id": log["id"],
           "platform": platform,
           "account": log.get("account_name", ""),
           "url": log.get("url", ""),
           "tid": tid,
           "old_status": "pending_review",
           "new_status": "pending_review",
           "updated": False,
       }

       if platform == "discuz" and tid:
           cfg_str = log.get("config_json", "{}")
           cfg = json.loads(cfg_str) if cfg_str else {}
           if not cfg:
               result["error"] = "无法获取账号配置"
               results.append(result)
               continue

           try:
               publisher = get_publisher("discuz", cfg)
               verify = publisher._verify_thread_exists(tid)
               if verify["status"] == "published":
                   conn.execute(
                       "UPDATE publish_log SET status='published', message='published' WHERE id=?",
                       (log["id"],)
                   )
                   result["new_status"] = "published"
                   result["updated"] = True
                   result["title"] = verify.get("title", "")
                   result["url"] = verify.get("url", log.get("url", ""))
                   updated_count += 1
               else:
                   result["error"] = verify.get("title", "仍为待审核状态")
           except Exception as e:
               result["error"] = f"检查异常: {e}"
       else:
           result["error"] = f"平台 {platform} 暂不支持自动检查"

       results.append(result)

   conn.commit()

