"""
Forum & Platform Registry — 统一智能版块匹配系统（双轨读取：JSON + DB）

存储所有平台的版块/分类/项目类型数据，根据文章内容自动匹配。
支持从 JSON 文件和 flashsloth.db 双轨读取，优先使用 DB 数据。
"""
import json, os, re, sys, sqlite3
from typing import Optional

# ============================================================
# 0. 配置：读取模式
# ============================================================
# "auto"  — DB优先，DB无数据时fallback到JSON（推荐 · 默认）
# "json"  — 仅从JSON文件读取（传统模式）
# "db"    — 仅从DB读取
REGISTRY_MODE = os.environ.get("FORUM_REGISTRY_MODE", "auto")

# ============================================================
# 1. 论坛/平台版块数据库
# ============================================================

# 数据结构：
# {domain: {fid: {"name": str, "can_post": bool, "keywords": [str]}}}

FORUM_DATA = {}
PLATFORM_CATEGORIES = {}
_loaded_from_db = False
_loaded_from_json = False

_data_dir = os.path.join(os.path.dirname(__file__), "..", "platform_reports")
_data_dir = os.path.abspath(_data_dir)

_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flashsloth.db")


# ── DB 读取 ──────────────────────────────────────────────
def _load_from_db() -> dict:
    """从 flashsloth.db 的 forum_exploration 表加载版块数据。

    只加载实际论坛平台（排除 oshwhub.com、csdn.net 等非论坛内容平台）。
    """
    if not os.path.exists(_db_path):
        return {}

    # 非论坛平台：这些是内容平台，它们的 forum_exploration 记录
    # 只是项目类型/文章类型，不应进入 FORUM_DATA
    _NON_FORUM_DOMAINS = {"oshwhub.com", "csdn.net"}

    try:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT platform_domain, section_id, section_name, keywords, "
            "extra_info, tags_of_interest "
            "FROM forum_exploration WHERE can_post=1"
        ).fetchall()
        conn.close()

        def _parse_json_field(val: str, fallback: list | dict):
            if isinstance(val, str) and val.strip():
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            return fallback

        result: dict = {}
        for r in rows:
            domain = r["platform_domain"]
            if not domain or domain in _NON_FORUM_DOMAINS:
                continue
            if domain not in result:
                result[domain] = {}

            raw_kw = r["keywords"] or "[]"
            kw = _parse_json_field(raw_kw, [r["section_name"]])
            if not kw:
                kw = [r["section_name"]]

            entry: dict = {
                "name": r["section_name"],
                "keywords": kw,
            }

            # 携带 extra_info 和 tags_of_interest（为后续完全迁移到DB做准备）
            extra = _parse_json_field(r["extra_info"], {})
            if extra:
                entry["extra_info"] = extra
            toi = _parse_json_field(r["tags_of_interest"], [])
            if toi:
                entry["tags_of_interest"] = toi

            result[domain][r["section_id"]] = entry
        return result
    except Exception as e:
        if REGISTRY_MODE == "db":
            print(f"[forum_registry] DB load failed (db-only mode): {e}", file=sys.stderr)
        return {}


# ── JSON 读取 ────────────────────────────────────────────
def _load_forum_json(filename: str) -> dict:
    path = os.path.join(_data_dir, filename)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def _load_forum_domain_from_json(domain: str, json_filename: str) -> None:
    """Load forum data for a domain from JSON, with keyword preservation."""
    data = _load_forum_json(json_filename)
    if data.get("forums"):
        FORUM_DATA[domain] = {}
        for fid, info in data["forums"].items():
            if info.get("can_post"):
                entry = {"name": info["name"]}
                if info.get("keywords"):
                    entry["keywords"] = info["keywords"]
                FORUM_DATA[domain][fid] = entry


def _load_all_from_json() -> None:
    """Load all JSON forum data (original behaviour)."""
    global _loaded_from_json
    if _loaded_from_json:
        return
    _loaded_from_json = True

    # 加载 amobbs (先新文件名，fallback旧文件名)
    for jname in ["amobbs_com_forums.json", "amobbs_forums.json.bak"]:
        if os.path.exists(os.path.join(_data_dir, jname)):
            _load_forum_domain_from_json("amobbs.com", jname)
            break

    # 加载 mydigit
    for jname in ["mydigit_cn_forums.json", "mydigit_forums.json.bak"]:
        if os.path.exists(os.path.join(_data_dir, jname)):
            _load_forum_domain_from_json("mydigit.cn", jname)
            break


# ── 统一加载入口（按 REGISTRY_MODE） ─────────────────
def reload_registry(mode: Optional[str] = None) -> None:
    """
    重新加载论坛版块数据。

    参数:
        mode: "auto" / "json" / "db" — 覆盖当前 REGISTRY_MODE
    """
    global FORUM_DATA, _loaded_from_db, _loaded_from_json
    effective_mode = mode or REGISTRY_MODE

    FORUM_DATA.clear()
    _loaded_from_db = False
    _loaded_from_json = False

    if effective_mode == "json":
        _load_all_from_json()

    elif effective_mode == "db":
        db_data = _load_from_db()
        if db_data:
            FORUM_DATA.update(db_data)
        _loaded_from_db = True

    else:  # "auto" — DB 优先，JSON fallback 补缺
        db_data = _load_from_db()
        _loaded_from_db = True

        if db_data:
            FORUM_DATA.update(db_data)

        # JSON 填充 DB 中没有的域名
        _load_all_from_json()
        # 但不要覆盖 DB 已有的域名
        if db_data:
            for domain in db_data:
                FORUM_DATA.pop(domain, None)
            # 重新加回 DB 数据
            FORUM_DATA.update(db_data)

    # 重建关键词索引
    _build_keyword_index()


# ============================================================
# 2. 非论坛平台分类 (OSHWHub, CSDN)
# ============================================================

PLATFORM_CATEGORIES = {
    "oshwhub.com": {
        "project_types": [
            {"id": "project", "name": "工程", "endpoint": "/project/create", "desc": "开源硬件工程"},
            {"id": "article", "name": "文章", "endpoint": "/article/create", "desc": "技术文章/教程"},
        ],
        "tags": [
            "5G/5G技术", "智能硬件", "课设/毕设", "DIY设计", "汽车电子",
            "消费电子", "工业电子", "家用电子", "医疗电子", "开源复刻",
            "电力电子", "电路仿真", "测量仪表", "电工电子", "电路模块",
            "星火计划2026", "星火计划2025", "星火计划2024", "星火计划2023",
            "训练营", "征集令", "立创大赛", "电子设计大赛", "蓝桥杯大赛",
            "3D打印", "CNC加工", "FPC软板", "方案验证板", "功能模块", "成品/套件",
        ],
    },
    "csdn.net": {
        "content_types": [
            {"id": "original", "name": "原创"},
            {"id": "reprint", "name": "转载"},
            {"id": "translation", "name": "翻译"},
        ],
        "editor_url": "https://editor.csdn.net/md/",
    }
}


# ============================================================
# 3. Auto-generate keywords from forum names
# ============================================================

def _generate_keywords(name: str) -> list:
    """根据版块名称自动生成匹配关键词"""
    keywords = [name.lower()]

    # 常见分割符
    parts = re.split(r'[/、,，&\s]+', name)
    for p in parts:
        p = p.strip().lower()
        if p and len(p) >= 2 and p not in keywords:
            keywords.append(p)

    # 常见别名映射
    alias_map = {
        "单片机": ["mcu", "microcontroller", "esp32", "esp8266", "nrf", "ch32", "gd32", "stc"],
        "stm32": ["stm32", "stm", "cortex"],
        "fpga": ["fpga", "verilog", "vhdl"],
        "linux": ["linux", "ubuntu", "debian"],
        "树莓派": ["raspberry pi", "树莓派"],
        "arduino": ["arduino"],
        "pcb": ["pcb", "layout", "电路板"],
        "电机": ["电机", "马达", "motor"],
        "3d打印": ["3d打印", "3d printer", "3dp"],
        "ai": ["ai", "人工智能", "machine learning", "deep learning"],
        "机器人": ["机器人", "robot"],
        "无人机": ["无人机", "drone", "飞控"],
        "wifi": ["wifi", "无线", "无线网络"],
        "蓝牙": ["蓝牙", "bluetooth"],
        "传感器": ["传感器", "sensor"],
        "arm": ["arm", "imx", "cortex-a"],
        "家电维修": ["维修", "家电维修", "修理", "fix"],
        "电池": ["电池", "battery", "锂电", "充电"],
        "汽车": ["汽车", "car", "电动车", "ev"],
        "智能家居": ["智能家居", "home assistant", "智能", "smart home"],
        "通信": ["通信", "网络", "networking", "lora", "zigbee"],
        "电源": ["电源", "power", "buck", "boost", "dc-dc", "开关电源"],
        "mcu": ["mcu", "单片机", "微控制器", "esp32", "esp8266", "嵌入式"],
    }

    for k, aliases in alias_map.items():
        if k in name.lower():
            for a in aliases:
                if a not in keywords:
                    keywords.append(a)

    return keywords


def _build_keyword_index():
    """为所有已注册论坛自动生成关键词"""
    for domain, forums in FORUM_DATA.items():
        for fid, info in forums.items():
            if "keywords" not in info:
                info["keywords"] = _generate_keywords(info["name"])


# ============================================================
# 4. 智能匹配引擎
# ============================================================

def match_forum(domain: str, tags: list, title: str = "", body: str = "") -> Optional[str]:
    """
    根据文章标签+标题+正文，匹配最佳版块FID

    Args:
        domain: 平台域名 (e.g. 'amobbs.com', 'mydigit.cn')
        tags: 文章标签列表
        title: 文章标题
        body: 文章正文

    Returns:
        fid (str) 或 None
    """
    forums = FORUM_DATA.get(domain)
    if not forums:
        return None

    text = " ".join(tags) + " " + title + " " + (body or "")[:200]
    text_lower = text.lower()

    # 计分匹配：优先匹配版块名本身，别名关键词权重减半
    scores = {}
    for fid, info in forums.items():
        score = 0
        forum_name_lower = info.get("name", "").lower()
        keywords = info.get("keywords", [forum_name_lower])

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                # 核心加权：关键词直接是版块名或版块名的一部分 → 权重更高
                if kw_lower == forum_name_lower or forum_name_lower.startswith(kw_lower):
                    score += 3
                # 别名关键词（从 alias_map 来的）权重较低
                else:
                    score += 1

        # 额外：如果用户的标签/标题关键词直接出现在版块名中 → 奖励
        for tag_word in tags + [title]:
            tw = tag_word.lower().strip()
            if tw and len(tw) >= 2 and tw in forum_name_lower:
                score += 2

        if score > 0:
            scores[fid] = score

    if scores:
        # 得分相同优先选名称更短的（更泛用的版块，而非具体项目）
        best = max(scores, key=lambda k: (scores[k], -len(forums[k].get("name", ""))))
        return best

    # 无匹配 → 返回默认版块
    defaults = {
        "amobbs.com": "3020",    # STM32/8
        "mydigit.cn": "59",       # 电子学堂
    }
    return defaults.get(domain)


def get_forum_name(domain: str, fid: str) -> str:
    """获取版块名称"""
    forums = FORUM_DATA.get(domain, {})
    info = forums.get(fid, {})
    return info.get("name", f"fid={fid}")


def list_postable_forums(domain: str) -> dict:
    """列出某平台所有可发帖版块"""
    return dict(FORUM_DATA.get(domain, {}))


def match_platform_type(platform: str, tags: list, title: str = "", body: str = "") -> dict:
    """
    OSHWHub/CSDN 等非论坛平台的类型匹配

    Returns:
        {"type_id": str, "type_name": str, "tags": list}
    """
    if platform == "oshwhub.com":
        categories = PLATFORM_CATEGORIES.get("oshwhub.com", {})
        project_types = categories.get("project_types", [])

        text = " ".join(tags) + " " + title + " " + (body or "")[:200]
        text_lower = text.lower()

        project_kw = ["工程", "项目", "硬件", "pcb", "原理图", "电路", "设计", "制作", "开源"]
        article_kw = ["教程", "文章", "笔记", "教程", "指南", "入门", "学习", "分享", "经验"]

        project_score = sum(1 for kw in project_kw if kw in text_lower)
        article_score = sum(1 for kw in article_kw if kw in text_lower)

        if project_score >= article_score and project_score > 0:
            return {"type_id": "project", "type_name": "工程", "endpoint": "/project/create"}
        elif article_score > 0:
            return {"type_id": "article", "type_name": "文章", "endpoint": "/article/create"}

        return {"type_id": "project", "type_name": "工程", "endpoint": "/project/create"}

    elif platform == "csdn.net":
        return {"type_id": "original", "type_name": "原创"}

    return {}


def get_platform_info(domain: str) -> dict:
    """获取平台完整信息"""
    info = {"domain": domain, "type": "unknown", "forums": {}, "categories": {}}

    if domain in FORUM_DATA:
        info["type"] = "discuz_forum"
        info["forums"] = FORUM_DATA[domain]
        info["postable_count"] = len(FORUM_DATA[domain])
        info["default_fid"] = {"amobbs.com": "3020", "mydigit.cn": "59"}.get(domain)

    if domain in PLATFORM_CATEGORIES:
        info["type"] = "content_platform"
        info["categories"] = PLATFORM_CATEGORIES[domain]

    return info


def register_forum_match(platform: str, site_url: str, tags: list,
                         title: str = "", body: str = "") -> dict:
    """一站式：匹配版块"""
    fid = match_forum(platform, tags, title, body)
    if fid:
        name = get_forum_name(platform, fid)
        return {"fid": fid, "source": "keyword", "name": name}

    return {"fid": None, "source": "no_match"}


# ── 模块初始化 ──────────────────────────────────────────
reload_registry()
