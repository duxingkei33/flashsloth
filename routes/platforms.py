"""Platforms routes — 平台预设路由"""
from flashsloth.routes._app import app
from flask import jsonify
import os, json
from flask_login import login_required

_PRESETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "core", "platform_presets.json")

# 平台图标/颜色映射（前端使用）
PLATFORM_ICONS = {
    'discuz': '💬', 'amobbs': '💬', 'mydigit': '💬',
    'oshwhub': '🔧', 'oshwhub_eda': '⚡',
    'csdn': '📝', 'cnblogs': '📖',
    'zhihu': '❓', 'bilibili': '📺', 'juejin': '🥇',
    'wechat': '💬', 'wechat_mp': '📢',
    'xianyu': '🐟', 'xianyu_v2': '🐟', 'taobao': '🛒',
    'wordpress': '🔗', 'github_pages': '📄', 'github_pages_blog': '📄',
    'static_site': '🌐', 'github': '🐙',
    'douyin': '🎵', 'kuaishou': '📱', 'xiaohongshu': '📕',
    'tieba': '📋', 'jianshu': '✍️', 'medium': '✏️',
    'segmentfault': '💻', 'v2ex': '🔶', 'hackernews': '🔴',
    'qqzone': '💫', 'weibo': '📢', 'toutiao': '📰',
    'smzdm': '💰', 'dewu': '👟',
    'default': '🔑',
}
PLATFORM_COLORS = {
    'discuz': '#e8f5e9', 'amobbs': '#e3f2fd', 'mydigit': '#fce4ec',
    'oshwhub': '#fff3e0', 'oshwhub_eda': '#fff8e1',
    'csdn': '#e8eaf6', 'cnblogs': '#f3e5f5',
    'zhihu': '#e0f2f1', 'bilibili': '#fce4ec', 'juejin': '#e8f5e9',
    'wechat': '#e8f5e9', 'wechat_mp': '#e3f2fd',
    'xianyu': '#fff3e0', 'xianyu_v2': '#fff3e0', 'taobao': '#fce4ec',
    'wordpress': '#e8eaf6', 'github_pages': '#f5f5f5', 'github_pages_blog': '#f5f5f5',
    'static_site': '#f5f5f5', 'github': '#f5f5f5',
    'douyin': '#fce4ec', 'kuaishou': '#fff3e0', 'xiaohongshu': '#fce4ec',
    'tieba': '#e3f2fd', 'jianshu': '#f3e5f5', 'medium': '#f5f5f5',
    'segmentfault': '#e8f5e9', 'v2ex': '#fff8e1', 'hackernews': '#fce4ec',
    'qqzone': '#e3f2fd', 'weibo': '#fce4ec', 'toutiao': '#fff3e0',
    'smzdm': '#fff3e0', 'dewu': '#e8f5e9',
    'default': '#f0f4ff',
}


@login_required
def _platforms_icons_json():
    """返回平台图标映射（可被前端/模板复用）"""
    return PLATFORM_ICONS


@login_required
def _platforms_colors_json():
    """返回平台颜色映射（可被前端/模板复用）"""
    return PLATFORM_COLORS


@app.route("/api/platforms/metadata")
@login_required
def api_platforms_metadata():
    """返回所有平台的图标和颜色映射（前端用）"""
    return jsonify({
        "success": True,
        "icons": PLATFORM_ICONS,
        "colors": PLATFORM_COLORS,
    })


@app.route("/api/platforms/presets")
@login_required
def api_platform_presets():
   """获取所有预设平台配置"""
   if os.path.exists(_PRESETS_PATH):
       with open(_PRESETS_PATH, "r", encoding="utf-8") as f:
           data = json.load(f)
       return jsonify({"success": True, "presets": data.get("presets", {})})
   return jsonify({"success": True, "presets": {}})

