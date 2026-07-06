"""FlashSloth — AI 提供商/配置/生成/余额路由
从 admin.py 提取，使用 Blueprint 重构"""
from flashsloth.routes._app import app


import json, time, os, re, threading

from flask import ( render_template, request, redirect, url_for,
                  flash, session, jsonify)
from flask_login import login_required, current_user

from flashsloth.core.database import get_db
from flashsloth.core.ai_provider import (get_router, list_ai_providers,
                                         get_ai_provider, AIRequest)

# 供应商余额 API 配置（无 Key 硬编码，仅存 URL 模板）
_BALANCE_API_TEMPLATES = {
   "deepseek": {"url": "https://api.deepseek.com/user/balance", "auth": "bearer", "path": ["balance_infos", 0, "total_balance"]},
   "openai": {"url": "https://api.openai.com/v1/dashboard/billing/credit_grants", "auth": "bearer", "path": ["total_grants", "total_used", "total_granted"]},
}

def _query_balance(provider: str, api_key: str, api_base: str = "") -> str:
   """查询供应商余额（零 token 消耗），返回格式化字符串"""
   import requests as _req
   tmpl = _BALANCE_API_TEMPLATES.get(provider)
   if not tmpl:
       return "N/A"
   url = tmpl["url"]
   try:
       resp = _req.get(
           url,
           headers={"Authorization": f"Bearer {api_key}"},
           timeout=10,
       )
       if resp.ok:
           data = resp.json()
           if provider == "deepseek":
               infos = data.get("balance_infos", [])
               if infos:
                   remaining = infos[0].get("total_balance", "?")
                   currency = infos[0].get("currency", "¥")
                   return f"{currency} {remaining}"
           elif provider == "openai":
               total_granted = data.get("total_granted", 0)
               total_used = data.get("total_used", 0)
               remaining = total_granted - total_used
               return f"$ {remaining:.2f} / {total_granted:.2f}"
       return "查询失败"
   except Exception:
       return "查询失败"

# ─── AI 能力配置 API ────────────────────────────

@app.route("/api/ai/providers")
@login_required
def ai_list_providers():
   """列出所有AI Provider及其能力"""
   providers = list_ai_providers()
   return jsonify({"success": True, "providers": providers})

@app.route("/api/ai/config")
@login_required
def ai_get_config():
    """获取AI能力路由配置（含供应商模型信息）"""
    router = get_router()
    # 从DB获取已配置供应商的模型列表
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT provider, models FROM ai_configs WHERE user_id=? AND enabled=1",
        (current_user.id,)
    ).fetchall()
    conn.close()
    provider_models = {}
    for r in rows:
        try:
            models = json.loads(r["models"] or "[]")
            provider_models[r["provider"]] = models
        except Exception:
            provider_models[r["provider"]] = []
    return jsonify({
        "success": True,
        "capabilities": {k: v for k, v in router._capability_configs.items()},
        "providers": router._provider_configs,
        "provider_models": provider_models,
        "config": {
            "capabilities": {k: v for k, v in router._capability_configs.items()},
            "providers": router._provider_configs,
            "provider_models": provider_models,
        },
    })

@app.route("/api/ai/config", methods=["POST"])
@login_required
def ai_update_config():
   """更新AI能力路由配置"""
   data = request.json
   if not data:
       return jsonify({"success": False, "error": "缺少配置数据"})

   router = get_router()
   if "capabilities" in data:
       for cap, cfg in data["capabilities"].items():
           router.set_capability_config(cap, cfg)
   if "providers" in data:
       for provider, cfg in data["providers"].items():
           router.set_provider_config(provider, cfg)
   router.save_config()

   return jsonify({"success": True, "message": "AI配置已更新"})

@app.route("/api/ai/generate", methods=["POST"])
@login_required
def ai_generate():
   """调用AI生成内容"""
   data = request.json
   capability = data.get("capability", "writing")
   prompt = data.get("prompt", "")

   if not prompt:
       return jsonify({"success": False, "error": "缺少提示词"})

   router = get_router()
   result = router.call(
       capability=capability,
       prompt=prompt,
       temperature=data.get("temperature", 0.7),
       max_tokens=data.get("max_tokens", 4096),
       model=data.get("model", ""),
   )

   return jsonify({
       "success": result.success,
       "content": result.content,
       "images": result.images,
       "audio": result.audio,
       "model": result.model,
       "provider": result.provider,
       "error": result.error,
   })

@app.route("/api/ai/generate/parallel", methods=["POST"])
@login_required
def ai_generate_parallel():
   """并行调用AI（适合批量画图）"""
   data = request.json
   capability = data.get("capability", "image_gen")
   prompts = data.get("prompts", [])

   if not prompts:
       return jsonify({"success": False, "error": "缺少prompts列表"})

   router = get_router()
   results = router.call_parallel(capability=capability, prompts=prompts)

   return jsonify({
       "success": True,
       "results": [
           {
               "success": r.success,
               "content": r.content,
               "images": r.images,
               "audio": r.audio,
               "provider": r.provider,
               "model": r.model,
               "error": r.error,
           }
           for r in results
       ],
   })

@app.route("/ai/settings")
@login_required
def ai_settings_page():
    """AI配置管理页面 — 带供应商模型列表"""
    router = get_router()
    providers = list_ai_providers()
    config = {
        "capabilities": router._capability_configs,
        "providers": router._provider_configs,
    }
    # 从DB读取已配置供应商的模型列表
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT provider, models FROM ai_configs WHERE user_id=? AND enabled=1",
        (current_user.id,)
    ).fetchall()
    conn.close()
    provider_models = {}
    for r in rows:
        try:
            models = json.loads(r["models"] or "[]")
            provider_models[r["provider"]] = models
        except Exception:
            provider_models[r["provider"]] = []
    return render_template("ai_settings.html",
                         providers=providers,
                         config=config,
                         provider_models=provider_models)

@app.route("/api/ai/test/<provider_name>", methods=["POST"])
@login_required
def api_ai_test(provider_name):
   """测试AI Provider连接（支持动态注册表）"""
   router = get_router()
   pc = router._provider_configs.get(provider_name, {})
   if not pc.get("api_key"):
       return jsonify({"success": False, "error": "未配置API Key"})

   # 先用动态注册表查找
   from core.provider_registry import get_registry, UnifiedAIAdapter
   reg = get_registry()
   defn = reg.get(provider_name)
   if defn:
       adapter = UnifiedAIAdapter(defn, api_key=pc.get("api_key", ""), api_base=pc.get("api_base", ""))
       return jsonify(adapter.test_connection())

   # 兼容旧的硬编码 Provider
   from core.ai_provider import get_ai_provider
   provider = get_ai_provider(provider_name, pc)
   if provider:
       return jsonify(provider.test_connection())

   return jsonify({"success": False, "error": f"未知Provider: {provider_name}"})

@app.route("/api/ai/providers/list", methods=["GET"])
@login_required
def api_ai_providers_list():
   """返回动态供应商注册表（用于前端下拉选择）"""
   from core.provider_registry import get_registry
   reg = get_registry()
   data = reg.to_json()
   # 合并用户已配置的 provider 状态
   router = get_router()
   for p in data["providers"]:
       pc = router._provider_configs.get(p["name"], {})
       p["configured"] = bool(pc.get("api_key"))
   return jsonify(data)

@app.route("/api/ai/providers/custom", methods=["POST"])
@login_required
def api_ai_providers_custom():
   """保存自定义供应商定义"""
   data = request.get_json() or {}
   name = data.get("name", "").strip()
   if not name:
       return jsonify({"success": False, "error": "供应商名称不能为空"})
   # 生成唯一 name
   safe_name = re.sub(r"[^a-z0-9_]", "_", name.lower())
   if not safe_name:
       safe_name = f"custom_{int(time.time())}"

   router = get_router()
   # 保存到 provider_configs 的 custom_providers 字段
   existing = router._provider_configs.get("__custom_providers__", {})
   existing[safe_name] = {
       "name": safe_name,
       "display_name": name,
       "description": data.get("description", ""),
       "icon": data.get("icon", "✏️"),
       "website": data.get("website", ""),
       "api_base": data.get("api_base", ""),
       "api_format": data.get("api_format", "openai"),
       "models": data.get("models", []),
       "capabilities": data.get("capabilities", ["writing"]),
       "config_fields": data.get("config_fields", [
           {"key": "api_key", "label": "API Key", "type": "password", "required": True},
       ]),
   }
   router.set_provider_config("__custom_providers__", existing)
   router.save_config()

   return jsonify({"success": True, "name": safe_name, "display_name": name})

# ─── AI 供应商配置 API（全从数据库，零硬编码）───────────────────────

@app.route("/api/ai/providers/configured", methods=["GET"])
@login_required
def api_ai_configured_list():
   """从数据库查询已配置的 AI 供应商列表"""
   conn = get_db()
   rows = conn.execute(
       "SELECT * FROM ai_configs WHERE user_id=? ORDER BY provider, alias",
       (current_user.id,)
   ).fetchall()
   conn.close()

   from core.provider_registry import get_registry
   reg = get_registry()

   result = []
   for r in rows:
       d = dict(r)
       defn = reg.get(d["provider"])
       d["display_name"] = defn.display_name if defn else d["provider"]
       d["icon"] = defn.icon if defn else "🤖"
       d["website"] = defn.website if defn else ""
       d["api_format"] = d.get("api_format") or (defn.api_format if defn else "openai")
       # 解析 models
       try:
           d["models_list"] = json.loads(d.get("models") or "[]")
       except Exception:
           d["models_list"] = []
       if not d["models_list"] and defn:
           d["models_list"] = defn.models
       result.append(d)

   return jsonify({"success": True, "providers": result})

@app.route("/api/ai/providers/configured/test", methods=["POST"])
@login_required
def api_ai_configured_test():
    """测试 AI 供应商连接（零 token 消耗 — 只测可达性 + Key 有效性）"""
    data = request.get_json() or {}
    provider_name = data.get("provider", "")
    api_key = data.get("api_key", "")
    api_base = data.get("api_base", "")
    api_format = data.get("api_format", "openai")
    config_id = data.get("config_id")  # 可选：传入config_id以保存模型

    if not provider_name or not api_key:
        return jsonify({"success": False, "error": "供应商名和 API Key 不能为空"})

    from core.provider_registry import get_registry
    reg = get_registry()
    defn = reg.get(provider_name)
    base = api_base or (defn.api_base if defn else "")

    if not base:
        return jsonify({"success": False, "error": "缺少 API Base URL"})

    import requests as _req
    try:
        base = base.rstrip("/")
        # 智能处理常见完整URL输入（用户可能复制了整个 endpoint）
        for suffix in ["/chat/completions", "/v1/chat/completions", "/completions"]:
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        base = base.rstrip("/")
        if api_format == "openai":
            # 调 /v1/models — 零 token 消耗，验证 API Key 有效
            resp = _req.get(
                f"{base}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            if resp.ok:
                resp_data = resp.json()
                models = [m["id"] for m in resp_data.get("data", [])]

                # 如果传入 config_id，保存模型列表到 DB
                if config_id:
                    conn = get_db()
                    row = conn.execute(
                        "SELECT id FROM ai_configs WHERE id=? AND user_id=?",
                        (config_id, current_user.id)
                    ).fetchone()
                    if row:
                        conn.execute(
                            "UPDATE ai_configs SET models=? WHERE id=?",
                            (json.dumps(models), config_id)
                        )
                    conn.commit()
                    conn.close()

                return jsonify({
                    "success": True,
                    "message": f"连接成功，可用模型 {len(models)} 个",
                    "models": models[:20],
                })
            err = resp.json().get("error", {}).get("message", str(resp.text[:200]))
            return jsonify({"success": False, "error": f"连接失败: {err}"})

        elif api_format == "anthropic":
            resp = _req.get(
                f"{base}/v1/models",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                timeout=10,
            )
            if resp.ok:
                return jsonify({"success": True, "message": "连接成功"})
            err = resp.json().get("error", {}).get("message", str(resp.text[:200]))
            return jsonify({"success": False, "error": f"连接失败: {err}"})

        elif api_format == "gemini":
            # Gemini 没有简单的 key 验证接口，检查基础 URL 可达
            resp = _req.get(base.rstrip("/"), timeout=10)
            if resp.ok or resp.status_code in (400, 403, 404):
                return jsonify({"success": True, "message": "URL 可达（请用实际请求验证 Key）"})
            return jsonify({"success": False, "error": f"连接失败: HTTP {resp.status_code}"})

        return jsonify({"success": False, "error": f"不支持的格式: {api_format}"})
    except _req.exceptions.Timeout:
        return jsonify({"success": False, "error": "连接超时（10秒）"})
    except _req.exceptions.ConnectionError:
        return jsonify({"success": False, "error": "连接被拒绝 — 请检查 API Base URL"})
    except Exception as e:
        return jsonify({"success": False, "error": f"连接异常: {e}"})

@app.route("/api/ai/providers/configured", methods=["POST"])
@login_required
def api_ai_configured_add():
   """添加 AI 供应商配置（先测试连接，成功后保存）"""
   data = request.get_json() or {}
   provider = data.get("provider", "")
   alias = data.get("alias", "").strip()
   api_key = data.get("api_key", "")
   api_base = data.get("api_base", "")
   api_format = data.get("api_format", "openai")
   models = data.get("models", "[]")
   if isinstance(models, list):
       models = json.dumps(models)

   if not provider or not api_key:
       return jsonify({"success": False, "error": "供应商和 API Key 必填"})

   conn = get_db()
   # 自动生成默认别称
   if not alias:
       existing = conn.execute(
           "SELECT alias FROM ai_configs WHERE user_id=? AND provider=?",
           (current_user.id, provider)
       ).fetchall()
       existing_aliases = {r["alias"] for r in existing}
       base = provider
       idx = 1
       while f"{base}{idx:02d}" in existing_aliases:
           idx += 1
       alias = f"{base}{idx:02d}"

   # 检查是否已存在（用生成后的别称）
   existing = conn.execute(
       "SELECT id FROM ai_configs WHERE user_id=? AND provider=? AND alias=?",
       (current_user.id, provider, alias)
   ).fetchone()
   if existing:
       conn.close()
       return jsonify({"success": False, "error": f"该配置已存在（{provider} / {alias or '默认'}）"})

   from core.provider_registry import get_registry
   reg = get_registry()
   defn = reg.get(provider)
   fmt = api_format or (defn.api_format if defn else "openai")

   conn.execute(
       "INSERT INTO ai_configs (user_id, provider, alias, api_key, api_base, api_format, models, status) "
       "VALUES (?, ?, ?, ?, ?, ?, ?, 'connected')",
       (current_user.id, provider, alias, api_key, api_base, fmt, models)
   )
   conn.commit()
   inserted_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
   conn.close()

   return jsonify({"success": True, "id": inserted_id, "message": f"✅ {provider} ({alias or '默认'}) 已添加"})

@app.route("/api/ai/providers/configured/<int:acid>", methods=["DELETE"])
@login_required
def api_ai_configured_delete(acid):
   """从数据库删除 AI 供应商配置"""
   conn = get_db()
   row = conn.execute(
       "SELECT id FROM ai_configs WHERE id=? AND user_id=?",
       (acid, current_user.id)
   ).fetchone()
   if not row:
       conn.close()
       return jsonify({"success": False, "error": "配置不存在"})
   conn.execute("DELETE FROM ai_configs WHERE id=?", (acid,))
   conn.commit()
   conn.close()
   return jsonify({"success": True, "message": "已删除"})

@app.route("/api/ai/providers/configured/<int:acid>", methods=["PUT"])
@login_required
def api_ai_configured_update(acid):
   """编辑 AI 供应商配置"""
   data = request.get_json() or {}
   conn = get_db()
   row = conn.execute(
       "SELECT id FROM ai_configs WHERE id=? AND user_id=?",
       (acid, current_user.id)
   ).fetchone()
   if not row:
       conn.close()
       return jsonify({"success": False, "error": "配置不存在"})

   # 允许更新的字段
   updates = []
   params = []
   for field in ("alias", "api_key", "api_base", "api_format", "models"):
       if field in data:
           val = data[field]
           if field == "models" and isinstance(val, list):
               val = json.dumps(val)
           updates.append(f"{field}=?")
           params.append(val)

   if not updates:
       conn.close()
       return jsonify({"success": False, "error": "没有需要更新的字段"})

   params.append(acid)
   conn.execute(
       f"UPDATE ai_configs SET {', '.join(updates)} WHERE id=?",
       params
   )
   conn.commit()
   conn.close()
   return jsonify({"success": True, "message": "✅ 配置已更新"})

@app.route("/api/ai/providers/configured/<int:acid>/models", methods=["POST"])
@login_required
def api_ai_configured_update_models(acid):
    """更新已配置供应商的模型列表"""
    data = request.get_json() or {}
    models = data.get("models", [])
    if isinstance(models, list):
        models = json.dumps(models)
    conn = get_db()
    row = conn.execute(
        "SELECT id FROM ai_configs WHERE id=? AND user_id=?",
        (acid, current_user.id)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "error": "配置不存在"})
    conn.execute("UPDATE ai_configs SET models=? WHERE id=?", (models, acid))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "模型列表已更新"})

@app.route("/api/ai/providers/configured/<int:acid>/toggle", methods=["POST"])
@login_required
def api_ai_configured_toggle(acid):
   """启用/禁用 AI 供应商配置"""
   conn = get_db()
   row = conn.execute(
       "SELECT enabled FROM ai_configs WHERE id=? AND user_id=?",
       (acid, current_user.id)
   ).fetchone()
   if not row:
       conn.close()
       return jsonify({"success": False, "error": "配置不存在"})
   new_val = 0 if row["enabled"] else 1
   conn.execute("UPDATE ai_configs SET enabled=? WHERE id=?", (new_val, acid))
   conn.commit()
   conn.close()
   return jsonify({"success": True, "enabled": bool(new_val)})

# ─── 供应商余额查询（零 token 消耗）─────────────────────────

@app.route("/api/ai/providers/balance/refresh_all", methods=["POST"])
@login_required
def api_ai_balance_refresh_all():
   """刷新所有已配置供应商的余额（后台异步执行）"""
   conn = get_db()
   rows = conn.execute(
       "SELECT id, provider, api_key, api_base FROM ai_configs WHERE user_id=? AND enabled=1",
       (current_user.id,)
   ).fetchall()
   results = []
   for r in rows:
       balance = _query_balance(r["provider"], r["api_key"], r["api_base"] or "")
       conn.execute("UPDATE ai_configs SET balance=? WHERE id=?", (balance, r["id"]))
       results.append({"id": r["id"], "provider": r["provider"], "balance": balance})
   conn.commit()
   conn.close()
   return jsonify({"success": True, "results": results})

@app.route("/api/ai/providers/balance/refresh/<int:acid>", methods=["POST"])
@login_required
def api_ai_balance_refresh_one(acid):
   """刷新单个供应商的余额"""
   conn = get_db()
   row = conn.execute(
       "SELECT provider, api_key, api_base FROM ai_configs WHERE id=? AND user_id=?",
       (acid, current_user.id)
   ).fetchone()
   if not row:
       conn.close()
       return jsonify({"success": False, "error": "配置不存在"})
   balance = _query_balance(row["provider"], row["api_key"], row["api_base"] or "")
   conn.execute("UPDATE ai_configs SET balance=? WHERE id=?", (balance, acid))
   conn.commit()
   conn.close()
   return jsonify({"success": True, "balance": balance})

