"""
FlashSloth Router — 内容路由引擎

所有平台平等对待。从 A 采集 → 路由给 B 发布。
路由规则由用户定义，存储在 route_rules 表。
"""
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import sqlite3, json, os

from .adapter import Article, get_adapter, get_db, PlatformAdapter

CST = timezone(timedelta(hours=8))


# ═══════════════════════════════════════════════
# 路由规则
# ═══════════════════════════════════════════════

@dataclass
class RouteRule:
    """一条路由规则"""
    id: int = 0
    name: str = ""                       # 规则名
    source_platform: str = ""            # 来源平台（"*" = 全部）
    target_platform: str = ""            # 目标平台
    source_account_id: int = 0           # 来源账号（0 = 自动选）
    target_account_id: int = 0           # 目标账号（0 = 自动选）
    filter_keywords: str = ""            # AI 筛选关键词（空=全量）
    auto_publish: bool = False           # True=自动发，False=仅推荐
    max_daily: int = 10                  # 每日上限
    enabled: bool = True
    created_at: str = ""
    today_count: int = 0                 # 今日已发（非持久，运行时计算）


# ═══════════════════════════════════════════════
# 路由引擎
# ═══════════════════════════════════════════════

class Router:
    """
    路由引擎。
    """

    def __init__(self):
        self._ensure_tables()

    def _ensure_tables(self):
        """确保 route 相关表存在"""
        conn = get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS route_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_platform TEXT DEFAULT '*',
                target_platform TEXT NOT NULL,
                source_account_id INTEGER DEFAULT 0,
                target_account_id INTEGER DEFAULT 0,
                filter_keywords TEXT DEFAULT '',
                auto_publish INTEGER DEFAULT 0,
                max_daily INTEGER DEFAULT 10,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS route_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id INTEGER,
                article_title TEXT,
                source_platform TEXT,
                target_platform TEXT,
                source_url TEXT,
                target_url TEXT,
                success INTEGER DEFAULT 0,
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()

    # ─── 规则管理 ──────────────────────────────

    def list_rules(self) -> list[RouteRule]:
        conn = get_db()
        rows = conn.execute("SELECT * FROM route_rules ORDER BY id").fetchall()
        conn.close()
        return [RouteRule(**dict(r)) for r in rows]

    def add_rule(self, rule: RouteRule) -> int:
        conn = get_db()
        cur = conn.execute(
            "INSERT INTO route_rules (name, source_platform, target_platform, "
            "source_account_id, target_account_id, filter_keywords, "
            "auto_publish, max_daily, enabled) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (rule.name, rule.source_platform, rule.target_platform,
             rule.source_account_id, rule.target_account_id,
             rule.filter_keywords, int(rule.auto_publish),
             rule.max_daily, int(rule.enabled))
        )
        conn.commit()
        rid = cur.lastrowid
        conn.close()
        return rid

    def toggle_rule(self, rule_id: int, enabled: bool):
        conn = get_db()
        conn.execute("UPDATE route_rules SET enabled=? WHERE id=?", (int(enabled), rule_id))
        conn.commit()
        conn.close()

    def delete_rule(self, rule_id: int):
        conn = get_db()
        conn.execute("DELETE FROM route_rules WHERE id=?", (rule_id,))
        conn.commit()
        conn.close()

    # ─── 执行路由 ──────────────────────────────

    def route(self, article: Article, source_platform: str = "") -> list[dict]:
        """
        将一篇文章路由到所有匹配的目标平台。
        返回每条目标平台的发布结果。
        """
        results = []
        rules = self.list_rules()

        for rule in rules:
            if not rule.enabled:
                continue
            # 来源匹配
            if rule.source_platform != "*" and rule.source_platform != source_platform:
                continue
            # 关键词过滤
            if rule.filter_keywords:
                text = (article.title + " " + article.body).lower()
                if not any(kw.lower() in text for kw in rule.filter_keywords.split(",")):
                    continue
            # 每日上限
            today = datetime.now(CST).strftime("%Y-%m-%d")
            conn = get_db()
            cnt = conn.execute(
                "SELECT COUNT(*) FROM route_log WHERE rule_id=? AND date(created_at)=?",
                (rule.id, today)
            ).fetchone()[0]
            conn.close()
            if cnt >= rule.max_daily:
                continue

            # 获取目标 adapter
            target_adapter = get_adapter(rule.target_platform)
            if not target_adapter:
                continue

            # 执行发布
            if rule.auto_publish:
                result = target_adapter.publish(article)
            else:
                result = {"supported": True, "success": False, "message": "仅推荐，未自动发布"}

            # 记录日志
            conn = get_db()
            conn.execute(
                "INSERT INTO route_log (rule_id, article_title, source_platform, "
                "target_platform, source_url, target_url, success, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (rule.id, article.title, source_platform, rule.target_platform,
                 article.source_url, result.get("url", ""),
                 int(result.get("success", False)),
                 result.get("error", ""))
            )
            conn.commit()
            conn.close()

            results.append({
                "rule_id": rule.id,
                "target": rule.target_platform,
                "success": result.get("success", False),
                "url": result.get("url", ""),
                "error": result.get("error", ""),
                "message": result.get("message", ""),
            })

        return results

    def execute_all_rules(self) -> list[dict]:
        """
        执行所有规则：采集来源平台 → 路由到目标平台。
        适合 cron 定时调用。
        """
        all_results = []
        rules = self.list_rules()

        # 收集涉及的来源平台
        source_platforms = set()
        for rule in rules:
            if rule.enabled and rule.source_platform != "*":
                source_platforms.add(rule.source_platform)

        for sp in source_platforms:
            adapter = get_adapter(sp)
            if not adapter:
                continue
            posts = adapter.fetch_posts()
            for post in posts:
                results = self.route(post, source_platform=sp)
                all_results.extend(results)

        return all_results
