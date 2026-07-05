"""
CompiledCache — 编译产物数据库缓存

表结构:
  compiled_cache (
    id, article_id, platform, 
    title, body, rendered_html,
    warnings TEXT, image_warnings TEXT,
    source_hash TEXT,           -- 源文的 hash，用于判断是否需要重编译
    created_at, updated_at
  )

用法:
    cache = CompiledCache()
    cache.save(article_id, platform, compiled_data)
    cached = cache.load(article_id, platform)
    platforms = cache.get_platforms(article_id)
"""
import json, hashlib, time
from typing import Optional


class CompiledCache:
    """编译产物缓存管理"""

    TABLE_NAME = "compiled_cache"

    def __init__(self):
        self._ensure_table()

    def _get_db(self):
        """获取 DB 连接"""
        try:
            from flashsloth.core.database import get_db
            return get_db()
        except ImportError:
            from core.database import get_db
            return get_db()

    def _ensure_table(self):
        """确保表存在"""
        conn = self._get_db()
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                title TEXT DEFAULT '',
                body TEXT DEFAULT '',
                rendered_html TEXT DEFAULT '',
                warnings TEXT DEFAULT '[]',
                image_warnings TEXT DEFAULT '[]',
                error TEXT DEFAULT '',
                source_hash TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(article_id, platform)
            )
        """)
        conn.commit()
        conn.close()

    @staticmethod
    def _hash_source(article) -> str:
        """计算源文章的 hash，用于判断源文是否变更"""
        raw = f"{article.title}|{article.body}|{json.dumps(article.tags, ensure_ascii=False)}|{article.summary}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    def save(self, article_id: int, platform: str, data: dict) -> bool:
        """保存一条编译缓存"""
        conn = self._get_db()
        try:
            conn.execute(f"""
                INSERT INTO {self.TABLE_NAME}
                (article_id, platform, title, body, rendered_html,
                 warnings, image_warnings, error, source_hash, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(article_id, platform) DO UPDATE SET
                    title=excluded.title,
                    body=excluded.body,
                    rendered_html=excluded.rendered_html,
                    warnings=excluded.warnings,
                    image_warnings=excluded.image_warnings,
                    error=excluded.error,
                    source_hash=excluded.source_hash,
                    updated_at=datetime('now')
            """, (
                article_id, platform,
                data.get("title", ""),
                data.get("body", ""),
                data.get("rendered_html", ""),
                json.dumps(data.get("warnings", []), ensure_ascii=False),
                json.dumps(data.get("image_warnings", []), ensure_ascii=False),
                data.get("error", ""),
                data.get("source_hash", ""),
            ))
            conn.commit()
            return True
        except Exception as e:
            return False
        finally:
            conn.close()

    def load(self, article_id: int, platform: str) -> Optional[dict]:
        """加载一条编译缓存"""
        conn = self._get_db()
        row = conn.execute(
            f"SELECT * FROM {self.TABLE_NAME} WHERE article_id=? AND platform=?",
            (article_id, platform)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {
            "platform": row["platform"],
            "title": row["title"],
            "body": row["body"],
            "rendered_html": row["rendered_html"],
            "warnings": json.loads(row["warnings"]) if row["warnings"] else [],
            "image_warnings": json.loads(row["image_warnings"]) if row["image_warnings"] else [],
            "error": row["error"],
            "source_hash": row["source_hash"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_platforms(self, article_id: int) -> list[str]:
        """获取某篇文章的所有已缓存平台"""
        conn = self._get_db()
        rows = conn.execute(
            f"SELECT platform FROM {self.TABLE_NAME} WHERE article_id=? ORDER BY id",
            (article_id,)
        ).fetchall()
        conn.close()
        return [r["platform"] for r in rows]

    def is_fresh(self, article_id: int, platform: str, source_hash: str) -> bool:
        """检查缓存是否仍有效（源文未变）"""
        cached = self.load(article_id, platform)
        if not cached:
            return False
        return cached.get("source_hash") == source_hash

    def delete_article(self, article_id: int):
        """删除某篇文章的所有缓存"""
        conn = self._get_db()
        conn.execute(f"DELETE FROM {self.TABLE_NAME} WHERE article_id=?", (article_id,))
        conn.commit()
        conn.close()

    def delete_platform(self, article_id: int, platform: str):
        """删除某篇文章的某个平台缓存"""
        conn = self._get_db()
        conn.execute(
            f"DELETE FROM {self.TABLE_NAME} WHERE article_id=? AND platform=?",
            (article_id, platform)
        )
        conn.commit()
        conn.close()

    def save_batch(self, article_id: int, results: dict, source_hash: str):
        """批量保存编译缓存"""
        for platform, data in results.items():
            cache_data = {
                "title": data.get("title", ""),
                "body": data.get("body", ""),
                "rendered_html": data.get("rendered_html", ""),
                "warnings": data.get("warnings", []),
                "image_warnings": data.get("image_warnings", []),
                "error": data.get("error", ""),
                "source_hash": source_hash,
            }
            self.save(article_id, platform, cache_data)
