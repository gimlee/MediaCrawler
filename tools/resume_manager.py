# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from typing import Any, Optional

import config
from tools import utils


STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"


class ResumeManager:
    """Small SQLite-backed checkpoint store for page, detail and comment tasks."""

    def __init__(self) -> None:
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._resume_key = ""
        self._db_path = ""
        self._reset_done = False

    @property
    def enabled(self) -> bool:
        return bool(getattr(config, "ENABLE_RESUME", True))

    @property
    def resume_key(self) -> str:
        self._ensure_ready()
        return self._resume_key

    def _ensure_ready(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            resume_key = self._build_resume_key()
            if self._conn is not None and resume_key == self._resume_key:
                return

            self.close()
            self._resume_key = resume_key
            state_dir = getattr(config, "RESUME_STATE_DIR", "data/resume")
            os.makedirs(state_dir, exist_ok=True)
            self._db_path = os.path.join(state_dir, f"{resume_key}.sqlite")
            self._conn = sqlite3.connect(
                self._db_path,
                timeout=30,
                isolation_level=None,
                check_same_thread=False,
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=30000")
            self._create_tables()

            if getattr(config, "RESET_RESUME_STATE", False) and not self._reset_done:
                self.reset()
                self._reset_done = True

            utils.logger.info(
                f"[ResumeManager] Enabled, resume_key={self._resume_key}, db={self._db_path}"
            )

    def _build_resume_key(self) -> str:
        custom_task_id = str(getattr(config, "RESUME_TASK_ID", "") or "").strip()
        if custom_task_id:
            return self._safe_name(custom_task_id)

        payload = {
            "platform": getattr(config, "PLATFORM", ""),
            "crawler_type": getattr(config, "CRAWLER_TYPE", ""),
            "keywords": getattr(config, "KEYWORDS", ""),
            "start_page": getattr(config, "START_PAGE", ""),
            "max_notes": getattr(config, "CRAWLER_MAX_NOTES_COUNT", ""),
            "comments": getattr(config, "ENABLE_GET_COMMENTS", ""),
            "sub_comments": getattr(config, "ENABLE_GET_SUB_COMMENTS", ""),
            "comment_limit": getattr(config, "CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES", ""),
            "save": getattr(config, "SAVE_DATA_OPTION", ""),
        }
        digest = hashlib.sha1(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        prefix = self._safe_name(
            f"{payload['platform']}_{payload['crawler_type']}_{payload['save']}"
        )
        return f"{prefix}_{digest}"

    @staticmethod
    def _safe_name(value: str) -> str:
        value = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip())
        return value.strip("._-") or "default"

    def _create_tables(self) -> None:
        assert self._conn is not None
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS crawler_resume_pages (
                resume_key TEXT NOT NULL,
                platform TEXT NOT NULL,
                crawler_type TEXT NOT NULL,
                keyword TEXT NOT NULL,
                page INTEGER NOT NULL,
                cursor TEXT,
                status TEXT NOT NULL,
                fail_count INTEGER DEFAULT 0,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (resume_key, keyword, page)
            );

            CREATE TABLE IF NOT EXISTS crawler_resume_items (
                resume_key TEXT NOT NULL,
                platform TEXT NOT NULL,
                keyword TEXT,
                content_id TEXT NOT NULL,
                content_type TEXT,
                detail_status TEXT DEFAULT 'pending',
                comment_status TEXT DEFAULT 'pending',
                comment_cursor TEXT,
                comment_done_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (resume_key, platform, content_id)
            );
            """
        )

    def reset(self) -> None:
        if not self.enabled:
            return
        self._ensure_ready_without_reset()
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                "DELETE FROM crawler_resume_pages WHERE resume_key = ?",
                (self._resume_key,),
            )
            self._conn.execute(
                "DELETE FROM crawler_resume_items WHERE resume_key = ?",
                (self._resume_key,),
            )
            utils.logger.info(f"[ResumeManager] Reset resume state: {self._resume_key}")

    def _ensure_ready_without_reset(self) -> None:
        reset_value = getattr(config, "RESET_RESUME_STATE", False)
        config.RESET_RESUME_STATE = False
        try:
            self._ensure_ready()
        finally:
            config.RESET_RESUME_STATE = reset_value

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def is_page_done(self, keyword: str, page: int) -> bool:
        if not self.enabled:
            return False
        self._ensure_ready()
        row = self._fetchone(
            "SELECT status FROM crawler_resume_pages WHERE resume_key = ? AND keyword = ? AND page = ?",
            (self._resume_key, keyword, page),
        )
        return bool(row and row[0] == STATUS_DONE)

    def mark_page_running(self, keyword: str, page: int, cursor: str = "") -> None:
        self._upsert_page(keyword, page, STATUS_RUNNING, cursor)

    def mark_page_done(self, keyword: str, page: int, cursor: str = "") -> None:
        self._upsert_page(keyword, page, STATUS_DONE, cursor)

    def mark_page_failed(self, keyword: str, page: int, cursor: str = "") -> None:
        if not self.enabled:
            return
        self._ensure_ready()
        now = self._now()
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO crawler_resume_pages
                    (resume_key, platform, crawler_type, keyword, page, cursor, status, fail_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(resume_key, keyword, page) DO UPDATE SET
                    cursor = excluded.cursor,
                    status = CASE
                        WHEN crawler_resume_pages.fail_count + 1 >= ? THEN ?
                        ELSE ?
                    END,
                    fail_count = crawler_resume_pages.fail_count + 1,
                    updated_at = excluded.updated_at
                """,
                (
                    self._resume_key,
                    config.PLATFORM,
                    config.CRAWLER_TYPE,
                    keyword,
                    page,
                    cursor,
                    STATUS_FAILED,
                    now,
                    getattr(config, "RESUME_ITEM_MAX_FAILED_TIMES", 3),
                    STATUS_FAILED,
                    STATUS_RUNNING,
                ),
            )

    def _upsert_page(self, keyword: str, page: int, status: str, cursor: str = "") -> None:
        if not self.enabled:
            return
        self._ensure_ready()
        now = self._now()
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO crawler_resume_pages
                    (resume_key, platform, crawler_type, keyword, page, cursor, status, fail_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(resume_key, keyword, page) DO UPDATE SET
                    cursor = excluded.cursor,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    self._resume_key,
                    config.PLATFORM,
                    config.CRAWLER_TYPE,
                    keyword,
                    page,
                    cursor,
                    status,
                    now,
                ),
            )

    def upsert_item(
        self,
        content_id: Any,
        keyword: str = "",
        content_type: str = "",
    ) -> None:
        content_id = self._normalize_id(content_id)
        if not self.enabled or not content_id:
            return
        self._ensure_ready()
        now = self._now()
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO crawler_resume_items
                    (resume_key, platform, keyword, content_id, content_type, detail_status, comment_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(resume_key, platform, content_id) DO UPDATE SET
                    keyword = COALESCE(NULLIF(excluded.keyword, ''), crawler_resume_items.keyword),
                    content_type = COALESCE(NULLIF(excluded.content_type, ''), crawler_resume_items.content_type),
                    updated_at = excluded.updated_at
                """,
                (
                    self._resume_key,
                    config.PLATFORM,
                    keyword,
                    content_id,
                    content_type,
                    STATUS_PENDING,
                    STATUS_PENDING,
                    now,
                ),
            )

    def should_skip_detail(self, content_id: Any) -> bool:
        return self._status_is_done(content_id, "detail_status")

    def should_skip_comment(self, content_id: Any) -> bool:
        if not getattr(config, "ENABLE_GET_COMMENTS", True):
            return True
        return self._status_is_done(content_id, "comment_status")

    def mark_detail_running(self, content_id: Any, keyword: str = "", content_type: str = "") -> None:
        self.upsert_item(content_id, keyword, content_type)
        self._set_item_status(content_id, detail_status=STATUS_RUNNING)

    def mark_detail_done(self, content_id: Any, keyword: str = "", content_type: str = "") -> None:
        self.upsert_item(content_id, keyword, content_type)
        self._set_item_status(content_id, detail_status=STATUS_DONE)

    def mark_detail_failed(self, content_id: Any, keyword: str = "", content_type: str = "") -> None:
        self.upsert_item(content_id, keyword, content_type)
        self._increment_item_failure(content_id, "detail_status")

    def mark_comment_running(self, content_id: Any, keyword: str = "", content_type: str = "") -> None:
        self.upsert_item(content_id, keyword, content_type)
        self._set_item_status(content_id, comment_status=STATUS_RUNNING)

    def mark_comment_done(self, content_id: Any, keyword: str = "", content_type: str = "") -> None:
        self.upsert_item(content_id, keyword, content_type)
        self._set_item_status(content_id, comment_status=STATUS_DONE)

    def mark_comment_failed(self, content_id: Any, keyword: str = "", content_type: str = "") -> None:
        self.upsert_item(content_id, keyword, content_type)
        self._increment_item_failure(content_id, "comment_status")

    def _status_is_done(self, content_id: Any, column: str) -> bool:
        content_id = self._normalize_id(content_id)
        if not self.enabled or not content_id:
            return False
        self._ensure_ready()
        row = self._fetchone(
            f"SELECT {column} FROM crawler_resume_items WHERE resume_key = ? AND platform = ? AND content_id = ?",
            (self._resume_key, config.PLATFORM, content_id),
        )
        if not row:
            return False
        if row[0] == STATUS_DONE:
            return True
        if row[0] == STATUS_FAILED and not getattr(config, "RESUME_RETRY_FAILED", True):
            return True
        return False

    def _set_item_status(
        self,
        content_id: Any,
        detail_status: Optional[str] = None,
        comment_status: Optional[str] = None,
    ) -> None:
        content_id = self._normalize_id(content_id)
        if not self.enabled or not content_id:
            return
        self._ensure_ready()
        fields = []
        values: list[Any] = []
        if detail_status is not None:
            fields.append("detail_status = ?")
            values.append(detail_status)
        if comment_status is not None:
            fields.append("comment_status = ?")
            values.append(comment_status)
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(self._now())
        values.extend([self._resume_key, config.PLATFORM, content_id])
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                f"""
                UPDATE crawler_resume_items
                SET {", ".join(fields)}
                WHERE resume_key = ? AND platform = ? AND content_id = ?
                """,
                tuple(values),
            )

    def _increment_item_failure(self, content_id: Any, status_column: str) -> None:
        content_id = self._normalize_id(content_id)
        if not self.enabled or not content_id:
            return
        self._ensure_ready()
        with self._lock:
            assert self._conn is not None
            self._conn.execute(
                f"""
                UPDATE crawler_resume_items
                SET
                    {status_column} = CASE
                        WHEN fail_count + 1 >= ? THEN ?
                        ELSE ?
                    END,
                    fail_count = fail_count + 1,
                    updated_at = ?
                WHERE resume_key = ? AND platform = ? AND content_id = ?
                """,
                (
                    getattr(config, "RESUME_ITEM_MAX_FAILED_TIMES", 3),
                    STATUS_FAILED,
                    STATUS_PENDING,
                    self._now(),
                    self._resume_key,
                    config.PLATFORM,
                    content_id,
                ),
            )

    def _fetchone(self, sql: str, params: tuple[Any, ...]) -> Optional[tuple[Any, ...]]:
        with self._lock:
            assert self._conn is not None
            return self._conn.execute(sql, params).fetchone()

    @staticmethod
    def _normalize_id(content_id: Any) -> str:
        if content_id is None:
            return ""
        return str(content_id).strip()

    @staticmethod
    def _now() -> int:
        return int(time.time())


resume_manager = ResumeManager()
