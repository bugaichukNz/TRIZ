"""SQLite-хранилище истории TRIZ-анализов."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "sessions" / "triz.db"
LEGACY_JSON_PATH = PROJECT_ROOT / "data" / "sessions" / "history.json"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS history_entries (
    id TEXT PRIMARY KEY,
    problem TEXT NOT NULL,
    result_json TEXT NOT NULL,
    time_display TEXT NOT NULL,
    created_at TEXT NOT NULL,
    chat_session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_created_at
    ON history_entries (created_at DESC);
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

ACTIVE_CHAT_SESSION_KEY = "active_chat_session_id"


def _now_display() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_db_path(database_url: str | None = None) -> Path:
    """Преобразует DATABASE_URL в путь к файлу SQLite."""
    url = (database_url or settings.database_url or "").strip()
    if not url:
        return DEFAULT_DB_PATH
    if url.startswith("sqlite:///"):
        raw = url.removeprefix("sqlite:///")
        path = Path(raw)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    raise ValueError(f"Поддерживается только SQLite, получено: {url[:32]}…")


def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    return {
        "id": row["id"],
        "problem": row["problem"],
        "result": json.loads(row["result_json"]),
        "time": row["time_display"],
        "created_at": row["created_at"],
        "chat_session_id": row["chat_session_id"] if "chat_session_id" in keys else None,
    }


class SessionsStore:
    """История запросов в SQLite (новые записи — первыми)."""

    def __init__(
        self,
        db_path: Path | None = None,
        max_entries: int | None = None,
    ) -> None:
        self.db_path = db_path or resolve_db_path()
        self.max_entries = max_entries if max_entries is not None else settings.history_max_entries
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_SCHEMA)
        self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(history_entries)")}
        if cols and "chat_session_id" not in cols:
            conn.execute(
                "ALTER TABLE history_entries ADD COLUMN chat_session_id TEXT"
            )

    def _init_once(self) -> None:
        if self._initialized:
            return
        with self._connect() as conn:
            self._ensure_schema(conn)
            self._migrate_legacy_json(conn)
            conn.commit()
        self._initialized = True

    def _migrate_legacy_json(self, conn: sqlite3.Connection) -> None:
        if not LEGACY_JSON_PATH.is_file():
            return
        count = conn.execute("SELECT COUNT(*) FROM history_entries").fetchone()[0]
        if count > 0:
            return
        try:
            raw = json.loads(LEGACY_JSON_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Не удалось импортировать %s: %s", LEGACY_JSON_PATH, exc)
            return
        if not isinstance(raw, list):
            return
        for item in raw[: self.max_entries]:
            if not isinstance(item, dict) or "problem" not in item:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO history_entries
                    (id, problem, result_json, time_display, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item.get("id") or str(uuid.uuid4()),
                    item["problem"],
                    json.dumps(item.get("result") or {}, ensure_ascii=False),
                    item.get("time") or _now_display(),
                    item.get("created_at") or _now_iso(),
                ),
            )
        backup = LEGACY_JSON_PATH.with_suffix(".json.bak")
        LEGACY_JSON_PATH.rename(backup)
        logger.info("История импортирована из JSON в SQLite, бэкап: %s", backup)

    def _trim(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM history_entries
            WHERE id NOT IN (
                SELECT id FROM history_entries
                ORDER BY created_at DESC
                LIMIT ?
            )
            """,
            (self.max_entries,),
        )

    def list_entries(
        self,
        limit: int | None = None,
        *,
        summary: bool = False,
    ) -> list[dict[str, Any]]:
        self._init_once()
        cap = limit if limit is not None else self.max_entries
        with self._connect() as conn:
            if summary:
                rows = conn.execute(
                    """
                    SELECT id, problem, time_display, created_at, chat_session_id
                    FROM history_entries
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (cap,),
                ).fetchall()
                return [
                    {
                        "id": row["id"],
                        "problem": row["problem"],
                        "time": row["time_display"],
                        "created_at": row["created_at"],
                        "chat_session_id": row["chat_session_id"],
                    }
                    for row in rows
                ]
            rows = conn.execute(
                """
                SELECT id, problem, result_json, time_display, created_at, chat_session_id
                FROM history_entries
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (cap,),
            ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        self._init_once()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, problem, result_json, time_display, created_at, chat_session_id
                FROM history_entries
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def delete_entries_for_chat_sessions(self, session_ids: list[str]) -> int:
        if not session_ids:
            return 0
        self._init_once()
        placeholders = ",".join("?" * len(session_ids))
        with self._connect() as conn:
            cur = conn.execute(
                f"DELETE FROM history_entries WHERE chat_session_id IN ({placeholders})",
                session_ids,
            )
            conn.commit()
            return cur.rowcount

    def add_entry(
        self,
        problem: str,
        result: dict[str, Any],
        *,
        time_display: str | None = None,
        chat_session_id: str | None = None,
    ) -> dict[str, Any]:
        self._init_once()
        entry = {
            "id": str(uuid.uuid4()),
            "problem": problem,
            "result": result,
            "time": time_display or _now_display(),
            "created_at": _now_iso(),
            "chat_session_id": chat_session_id,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO history_entries
                    (id, problem, result_json, time_display, created_at, chat_session_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry["id"],
                    entry["problem"],
                    json.dumps(entry["result"], ensure_ascii=False),
                    entry["time"],
                    entry["created_at"],
                    entry["chat_session_id"],
                ),
            )
            self._trim(conn)
            conn.commit()
        return entry

    def replace_all(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._init_once()
        trimmed = entries[: self.max_entries]
        with self._connect() as conn:
            conn.execute("DELETE FROM history_entries")
            for item in trimmed:
                conn.execute(
                    """
                    INSERT INTO history_entries
                        (id, problem, result_json, time_display, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        item.get("id") or str(uuid.uuid4()),
                        item["problem"],
                        json.dumps(item.get("result") or {}, ensure_ascii=False),
                        item.get("time") or _now_display(),
                        item.get("created_at") or _now_iso(),
                    ),
                )
            conn.commit()
        return trimmed

    def get_app_state(self, key: str) -> str | None:
        self._init_once()
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else None

    def set_app_state(self, key: str, value: str | None) -> None:
        self._init_once()
        with self._connect() as conn:
            self._ensure_schema(conn)
            if value is None:
                conn.execute("DELETE FROM app_state WHERE key = ?", (key,))
            else:
                conn.execute(
                    """
                    INSERT INTO app_state (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, value),
                )
            conn.commit()

    def clear(self) -> None:
        self._init_once()
        with self._connect() as conn:
            conn.execute("DELETE FROM history_entries")
            conn.execute(
                "DELETE FROM app_state WHERE key = ?",
                (ACTIVE_CHAT_SESSION_KEY,),
            )
            conn.commit()
        logger.info("История очищена в БД: %s", self.db_path)
