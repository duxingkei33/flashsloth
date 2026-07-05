"""Platforms routes — 平台预设路由"""
from flashsloth.routes._app import app
from flask import jsonify
import os, json
from flask_login import login_required

_PRESETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "core", "platform_presets.json")

@app.route("/api/platforms/presets")
@login_required
def api_platform_presets():
   """获取所有预设平台配置"""
   if os.path.exists(_PRESETS_PATH):
       with open(_PRESETS_PATH, "r", encoding="utf-8") as f:
           data = json.load(f)
       return jsonify({"success": True, "presets": data.get("presets", {})})
   return jsonify({"success": True, "presets": {}})

