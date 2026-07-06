"""SQLite-хранилище промежуточных артефактов этапов TRIZ-анализа."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.llm.models import StageArtifact
from backend.sessions_store import resolve_db_path

logger = logging.getLogger(__name__)

_ARTIFACTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS stage_artifacts (
    id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    profile_hash TEXT NOT NULL,
    user_id TEXT,
    FOREIGN KEY (entry_id) REFERENCES history_entries(id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_stage_artifacts_entry_step
    ON stage_artifacts (entry_id, step_id);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArtifactsStore:
    """Промежуточные артефакты этапов, привязанные к записям history_entries."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or resolve_db_path()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_ARTIFACTS_SCHEMA)

    def _init_once(self) -> None:
        if self._initialized:
            return
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.commit()
        self._initialized = True

    def save(
        self,
        entry_id: str,
        step_id: str,
        payload: dict[str, Any],
        *,
        profile_hash: str,
        user_id: str | None = None,
    ) -> StageArtifact:
        self._init_once()
        created_at = _now_iso()
        artifact_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO stage_artifacts
                    (id, entry_id, step_id, payload_json, created_at, profile_hash, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id, step_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at,
                    profile_hash = excluded.profile_hash,
                    user_id = excluded.user_id
                """,
                (
                    artifact_id,
                    entry_id,
                    step_id,
                    json.dumps(payload, ensure_ascii=False),
                    created_at,
                    profile_hash,
                    user_id,
                ),
            )
            conn.commit()
        return StageArtifact(
            step_id=step_id,
            payload=payload,
            created_at=created_at,
            profile_hash=profile_hash,
        )

    def list_metadata(
        self, entry_id: str, *, user_id: str
    ) -> list[dict[str, str]] | None:
        """Метаданные артефактов entry; None если entry не найден или чужой."""
        self._init_once()
        with self._connect() as conn:
            entry = conn.execute(
                "SELECT id FROM history_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            ).fetchone()
            if entry is None:
                return None
            rows = conn.execute(
                """
                SELECT step_id, created_at, profile_hash
                FROM stage_artifacts
                WHERE entry_id = ? AND user_id = ?
                ORDER BY created_at ASC
                """,
                (entry_id, user_id),
            ).fetchall()
        return [
            {
                "step_id": row["step_id"],
                "created_at": row["created_at"],
                "profile_hash": row["profile_hash"],
            }
            for row in rows
        ]

    def load_all_with_metadata(
        self, entry_id: str, *, user_id: str
    ) -> dict[str, dict[str, Any]] | None:
        """Payload и profile_hash артефактов entry; None если entry не найден или чужой."""
        self._init_once()
        with self._connect() as conn:
            entry = conn.execute(
                "SELECT id FROM history_entries WHERE id = ? AND user_id = ?",
                (entry_id, user_id),
            ).fetchone()
            if entry is None:
                return None
            rows = conn.execute(
                """
                SELECT step_id, payload_json, profile_hash
                FROM stage_artifacts
                WHERE entry_id = ? AND user_id = ?
                ORDER BY created_at ASC
                """,
                (entry_id, user_id),
            ).fetchall()
        return {
            row["step_id"]: {
                "payload": json.loads(row["payload_json"]),
                "profile_hash": row["profile_hash"],
            }
            for row in rows
        }

    def load_all_payloads(
        self, entry_id: str, *, user_id: str
    ) -> dict[str, dict] | None:
        """Все payload артефактов entry; None если entry не найден или чужой."""
        loaded = self.load_all_with_metadata(entry_id, user_id=user_id)
        if loaded is None:
            return None
        return {step_id: item["payload"] for step_id, item in loaded.items()}

    def get(
        self, entry_id: str, step_id: str, *, user_id: str
    ) -> StageArtifact | None:
        self._init_once()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT sa.step_id, sa.payload_json, sa.created_at, sa.profile_hash
                FROM stage_artifacts sa
                INNER JOIN history_entries he ON he.id = sa.entry_id
                WHERE sa.entry_id = ? AND sa.step_id = ? AND he.user_id = ? AND sa.user_id = ?
                """,
                (entry_id, step_id, user_id, user_id),
            ).fetchone()
        if row is None:
            return None
        return StageArtifact(
            step_id=row["step_id"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
            profile_hash=row["profile_hash"],
        )
