"""Platforms routes — 平台预设路由"""
from flashsloth.routes._app import app
from flask import jsonify
import os, json, glob
from flask_login import login_required

_PRESETS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "core", "platform_presets.json")

_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "platform_reports")

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
# 平台中文显示名称（用于 metadata 和作为 fallback）
PLATFORM_DISPLAY_NAMES = {
    'amobbs': '阿莫论坛 (amobbs)',
    'mydigit': '数码之家 (mydigit)',
    'oshwhub': '立创开源硬件平台 (OSHWHub)',
    'oshwhub_eda': '立创EDA',
    'bilibili': '哔哩哔哩 (Bilibili)',
    'csdn': 'CSDN',
    'cnblogs': '博客园',
    'zhihu': '知乎',
    'juejin': '掘金',
    'wechat': '微信公众号',
    'wechat_mp': '微信公众号 (mp)',
    'smzdm': '什么值得买 (smzdm)',
    'xiaohongshu': '小红书',
    'dewu': '得物',
    'wordpress': 'WordPress',
    'xianyu': '闲鱼',
    'xianyu_v2': '闲鱼 v2',
    'taobao': '淘宝',
    'douyin': '抖音',
    'kuaishou': '快手',
    'tieba': '百度贴吧',
    'jianshu': '简书',
    'medium': 'Medium',
    'segmentfault': 'SegmentFault',
    'v2ex': 'V2EX',
    'hackernews': 'Hacker News',
    'qqzone': 'QQ空间',
    'weibo': '微博',
    'toutiao': '今日头条',
    'github_pages': 'GitHub Pages',
    'github_pages_blog': 'GitHub Pages 博客',
    'static_site': '静态站点',
    'github': 'GitHub',
    'discuz': 'Discuz! 论坛',
    'douban': '豆瓣',
    '51cto': '51CTO',
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
    """返回所有平台的图标、颜色映射 和 平台列表（含适配状态）（前端用）"""

    # ─── 从 platform_reports 收集所有有探索数据的平台 ───
    reports_platforms = set()
    login_cap_platforms = set()

    # 扫描 *_exploration_report.json
    for fpath in glob.glob(os.path.join(_REPORTS_DIR, "*_exploration_report.json")):
        fname = os.path.basename(fpath)
        pname = fname.replace("_exploration_report.json", "")
        reports_platforms.add(pname)

    # 扫描 *_login_capabilities.json
    for fpath in glob.glob(os.path.join(_REPORTS_DIR, "*_login_capabilities.json")):
        fname = os.path.basename(fpath)
        pname = fname.replace("_login_capabilities.json", "")
        login_cap_platforms.add(pname)

    # ─── 读取 platform_config 表 ───
    from flashsloth.core.database import get_db
    db = get_db()
    config_platforms = set()
    config_notes = {}
    config_methods = {}
    try:
        rows = db.execute("SELECT DISTINCT platform, config_json FROM platform_config").fetchall()
        for row in rows:
            pname = row["platform"]
            config_platforms.add(pname)
            cj = json.loads(row["config_json"]) if isinstance(row["config_json"], str) else (row["config_json"] or {})
            # 从 config_json 提取额外信息
            if "display_name" in cj:
                config_notes[pname] = cj.get("display_name", pname)
            methods = cj.get("login_methods", [])
            if methods:
                config_methods[pname] = methods
    except Exception:
        pass

    # ─── 合并：config + exploration + login_capabilities ───
    all_platform_names = config_platforms | reports_platforms | login_cap_platforms

    platforms = []
    for pname in sorted(all_platform_names):
        # 判断是否有适配（有登录能力数据 AND 有探索报告 AND 有 config 或 publisher）
        has_exploration = pname in reports_platforms
        has_login_cap = pname in login_cap_platforms
        has_config = pname in config_platforms
        adapted = has_exploration and has_login_cap

        # 合并 login_methods：先从 config_json，再从 login_capabilities JSON
        login_methods = config_methods.get(pname, [])
        if not login_methods:
            cap_path = os.path.join(_REPORTS_DIR, f"{pname}_login_capabilities.json")
            if os.path.exists(cap_path):
                try:
                    with open(cap_path, "r", encoding="utf-8") as f:
                        cap_data = json.load(f)
                    login_methods = cap_data.get("login_methods", [])
                except Exception:
                    pass

        # display_name
        display_name = config_notes.get(pname, PLATFORM_DISPLAY_NAMES.get(pname, pname.replace("_", " ").title()))

        # 从 JSON 文件补全 display_name
        if pname not in config_notes:
            # 尝试从 exploration_report 读取
            report_path = os.path.join(_REPORTS_DIR, f"{pname}_exploration_report.json")
            if os.path.exists(report_path):
                try:
                    with open(report_path, "r", encoding="utf-8") as f:
                        rd = json.load(f)
                    display_name = rd.get("display_name", display_name)
                except Exception:
                    pass
            # 尝试从 login_capabilities 读取
            cap_path = os.path.join(_REPORTS_DIR, f"{pname}_login_capabilities.json")
            if os.path.exists(cap_path):
                try:
                    with open(cap_path, "r", encoding="utf-8") as f:
                        cd = json.load(f)
                    display_name = cd.get("platform_name", cd.get("display_name", display_name))
                except Exception:
                    pass

        platforms.append({
            "name": pname,
            "display_name": display_name,
            "adapted": adapted,
            "has_exploration": has_exploration,
            "has_login_capabilities": has_login_cap,
            "has_config": has_config,
            "login_methods": login_methods,
            "method_count": len(login_methods),
        })

    return jsonify({
        "success": True,
        "icons": PLATFORM_ICONS,
        "colors": PLATFORM_COLORS,
        "platforms": platforms,
        "total": len(platforms),
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
