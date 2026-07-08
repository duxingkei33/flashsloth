"""
平台探索数据导入器 — 将 platform_reports/*.json 导入到 platform_exploration 表

架构重构（铁律#28，数据驱动）：
- 取代路由中直接读 JSON 文件的模式
- 服务启动时自动扫描导入
- 后续搜索 API 改从 DB 查询，毫秒级响应
"""

import json
import os
import glob
import logging

_logger = logging.getLogger("flashsloth.loader")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s"))
    _logger.addHandler(_handler)

# ─── 平台名 → JSON 文件名映射（与 helpers.py 保持一致）───
_PLATFORM_CAP_MAP = {
    "wechat": "wechat_mp",
    "xianyu_v2": "xianyu",
    "xianyu_sidecar": "xianyu",
    "xianyu_auto_reply": "xianyu",
    "xianyu_products": "xianyu",
    "discuz_amobbs": "amobbs",
    "discuz_mydigit": "mydigit",
}

# ─── 反向映射：JSON 文件名 → 平台名 ───
_REVERSE_CAP_MAP = {v: k for k, v in _PLATFORM_CAP_MAP.items()}


def _get_project_root():
    """获取项目根目录（core/ 的父目录）"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _infer_config_fields_from_cap(cap: dict) -> list:
    """从探索数据推导配置字段列表（与 helpers.py 保持逻辑一致）"""
    fields = set()
    methods = cap.get("login_methods", [])
    login_url = cap.get("login_url", "")
    engine = cap.get("engine", "")

    # Discuz 类平台需要 site_url（相对路径 login_url）
    if engine == "discuz" or "discuz" in (cap.get("note") or "").lower():
        fields.add("site_url")

    # 登录 URL 是相对路径 → 需要 site_url
    if login_url and not login_url.startswith("http"):
        fields.add("site_url")

    # 从登录方法推导
    for m in methods:
        method = m.get("method", "")
        if method == "password":
            fields.add("username")
            fields.add("password")
        elif method == "phone":
            fields.add("phone")

    # 默认至少需要 site_url
    if not fields:
        fields.add("site_url")

    return sorted(fields)


def _infer_architecture(note: str, engine: str) -> str:
    """从 note 和 engine 推断架构描述"""
    if engine == "discuz" or "discuz" in (note or "").lower():
        return "基于 Discuz! 架构"
    if engine == "oshwhub":
        return "基于 JLC SSO 体系"
    if engine == "generic":
        return ""
    return ""


def import_exploration_to_db():
    """扫描 platform_reports/ 目录，将探索数据导入 platform_exploration 表。

    数据来源：
    1. *_login_capabilities.json — 登录能力数据
    2. *_exploration_report.json — 完整探索报告（取 display_name）

    行为：
    - 已有记录则更新（按 platform 主键 INSERT OR REPLACE）
    - 新增则 INSERT
    """
    from flashsloth.core.database import get_db

    root = _get_project_root()
    reports_dir = os.path.join(root, "platform_reports")

    if not os.path.isdir(reports_dir):
        _logger.warning("platform_reports 目录不存在: %s", reports_dir)
        return 0

    conn = get_db()
    count = 0
    update_count = 0

    # ─── 第一轮：扫描 *_login_capabilities.json ───
    seen_platforms = set()
    for cap_path in sorted(glob.glob(os.path.join(reports_dir, "*_login_capabilities.json"))):
        fname = os.path.basename(cap_path)
        json_name = fname.replace("_login_capabilities.json", "")  # e.g. "amobbs"

        # 使用原始 JSON 文件名作为平台名（与旧搜索代码相同）
        # 不通过 _REVERSE_CAP_MAP 映射，保持平台名称一致性
        pname = json_name

        try:
            with open(cap_path, "r", encoding="utf-8") as f:
                cap = json.load(f)
        except Exception as e:
            _logger.warning("  跳过 %s: 读取失败: %s", fname, e)
            continue

        display_name = (
            cap.get("platform_name")
            or cap.get("display_name")
            or pname.replace("_", " ").title()
        )
        engine = cap.get("engine", "")
        login_url = cap.get("login_url", "")
        login_methods = json.dumps(cap.get("login_methods", []), ensure_ascii=False)
        note = cap.get("note", "")[:200]  # 截断到 200 字符
        raw_detection = json.dumps(cap.get("raw_detection", {}), ensure_ascii=False)
        config_fields = json.dumps(_infer_config_fields_from_cap(cap), ensure_ascii=False)
        architecture = _infer_architecture(note, engine)
        full_data = json.dumps(cap, ensure_ascii=False)

        # 验证码信息
        rd = cap.get("raw_detection", {})
        captcha_info = json.dumps({
            "has_captcha": bool(rd.get("has_captcha", False)),
            "captcha_type": rd.get("captcha_type"),
            "description": rd.get("captcha_description", ""),
        }, ensure_ascii=False)

        try:
            conn.execute(
                """INSERT OR REPLACE INTO platform_exploration
                   (platform, display_name, engine, login_url, login_methods,
                    config_fields, captcha_info, architecture, note,
                    raw_detection, full_data, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (pname, display_name, engine, login_url, login_methods,
                 config_fields, captcha_info, architecture, note,
                 raw_detection, full_data),
            )
            count += 1
            seen_platforms.add(pname)
        except Exception as e:
            _logger.warning("  插入/更新失败 %s: %s", pname, e)

    # ─── 第二轮：扫描 *_exploration_report.json（补充 display_name）───
    for report_path in sorted(glob.glob(os.path.join(reports_dir, "*_exploration_report.json"))):
        fname = os.path.basename(report_path)
        json_name = fname.replace("_exploration_report.json", "")
        # 使用原始文件名作为平台名（与 login_capabilities 保持一致性）
        pname = json_name

        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception as e:
            _logger.warning("  跳过报告 %s: 读取失败: %s", fname, e)
            continue

        # 如果该平台尚未导入，或需要补充 display_name
        report_display = report.get("display_name", "")
        if report_display and pname not in seen_platforms:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO platform_exploration
                       (platform, display_name, login_url, engine, note, full_data, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
                    (pname, report_display,
                     report.get("login_url", report.get("site_url", "")),
                     report.get("engine", ""),
                     report.get("note", "")[:200],
                     json.dumps(report, ensure_ascii=False)),
                )
                count += 1
                seen_platforms.add(pname)
                update_count += 1
            except Exception as e:
                _logger.warning("  从报告导入失败 %s: %s", pname, e)
        elif report_display and pname in seen_platforms:
            # 已有记录，更新 display_name（如果当前为空）
            try:
                existing = conn.execute(
                    "SELECT display_name FROM platform_exploration WHERE platform=?", (pname,)
                ).fetchone()
                if existing and not existing["display_name"]:
                    conn.execute(
                        "UPDATE platform_exploration SET display_name=?, updated_at=datetime('now') WHERE platform=?",
                        (report_display, pname),
                    )
                    update_count += 1
            except Exception:
                pass

    conn.commit()
    conn.close()

    _logger.info(
        "平台探索数据导入完成: %d 条记录, %d 条更新, 来源 %s",
        count, update_count, reports_dir,
    )
    return count


if __name__ == "__main__":
    # 独立运行测试
    logging.basicConfig(level=logging.INFO)
    total = import_exploration_to_db()
    print(f"导入完成: {total} 条记录")
