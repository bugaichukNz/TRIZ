"""SQLite-хранилище диалоговых сессий интервью."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.chat_brief import compile_interview_brief
from backend.llm.chat_prompt import CHAT_OPENING_MESSAGE, READY_FOR_ANALYSIS_MARKER
from backend.config import settings
from backend.sessions_store import resolve_db_path

logger = logging.getLogger(__name__)

STATUS_INTERVIEW = "interview"
STATUS_READY = "ready"
STATUS_ANALYZED = "analyzed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'interview',
    title TEXT,
    messages_json TEXT NOT NULL,
    brief TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated
    ON chat_sessions (updated_at DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_marker(text: str) -> tuple[str, bool]:
    if READY_FOR_ANALYSIS_MARKER not in text:
        return text, False
    cleaned = text.replace(READY_FOR_ANALYSIS_MARKER, "").strip()
    return cleaned, True


def _title_from_messages(messages: list[dict[str, str]]) -> str:
    for msg in messages:
        if msg.get("role") == "user" and (msg.get("content") or "").strip():
            return msg["content"].strip()[:120]
    return "Новый диалог"


def session_has_user_messages(messages: list[dict[str, str]]) -> bool:
    """Диалог считается начатым после первого сообщения пользователя."""
    return any(
        msg.get("role") == "user" and (msg.get("content") or "").strip()
        for msg in messages
    )


class ChatStore:
    """Сессии интервью TRIZ."""

    def __init__(self, db_path=None, max_sessions: int | None = None) -> None:
        from pathlib import Path

        self.db_path = db_path or resolve_db_path()
        self.max_sessions = (
            max_sessions if max_sessions is not None else settings.chat_sessions_max
        )

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(_SCHEMA)

    def _row_to_session(self, row: sqlite3.Row) -> dict[str, Any]:
        messages = json.loads(row["messages_json"])
        return {
            "id": row["id"],
            "status": row["status"],
            "title": row["title"],
            "messages": messages,
            "brief": row["brief"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _trim_sessions(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM chat_sessions
            WHERE id NOT IN (
                SELECT id FROM chat_sessions
                ORDER BY updated_at DESC
                LIMIT ?
            )
            """,
            (self.max_sessions,),
        )

    def _purge_empty_sessions(self, conn: sqlite3.Connection) -> None:
        """Удаляет черновики без ответа пользователя (только приветствие ассистента)."""
        conn.execute(
            """
            DELETE FROM chat_sessions
            WHERE title IS NULL AND status = ?
            """,
            (STATUS_INTERVIEW,),
        )

    def list_sessions(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Краткий список без разбора messages_json (быстрая загрузка меню)."""
        cap = limit if limit is not None else self.max_sessions
        with self._connect() as conn:
            self._ensure_schema(conn)
            self._purge_empty_sessions(conn)
            conn.commit()
            rows = conn.execute(
                """
                SELECT id, status, title, created_at, updated_at
                FROM chat_sessions
                WHERE title IS NOT NULL
                   OR status IN (?, ?)
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (STATUS_READY, STATUS_ANALYZED, cap),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "status": row["status"],
                "title": row["title"] or "Новый диалог",
                "message_count": 0,
                "brief": None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as conn:
            self._ensure_schema(conn)
            cur = conn.execute(
                "DELETE FROM chat_sessions WHERE id = ?",
                (session_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_sessions(self, session_ids: list[str]) -> int:
        if not session_ids:
            return 0
        placeholders = ",".join("?" * len(session_ids))
        with self._connect() as conn:
            self._ensure_schema(conn)
            cur = conn.execute(
                f"DELETE FROM chat_sessions WHERE id IN ({placeholders})",
                session_ids,
            )
            conn.commit()
            return cur.rowcount

    def delete_all_sessions(self) -> int:
        with self._connect() as conn:
            self._ensure_schema(conn)
            cur = conn.execute("DELETE FROM chat_sessions")
            conn.commit()
            return cur.rowcount

    def create_session(self) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        now = _now_iso()
        messages = [
            {"role": "assistant", "content": CHAT_OPENING_MESSAGE},
        ]
        with self._connect() as conn:
            self._ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO chat_sessions
                    (id, status, title, messages_json, brief, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    STATUS_INTERVIEW,
                    None,
                    json.dumps(messages, ensure_ascii=False),
                    None,
                    now,
                    now,
                ),
            )
            self._trim_sessions(conn)
            conn.commit()
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT * FROM chat_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def _save_messages(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        messages: list[dict[str, str]],
        *,
        status: str | None = None,
        title: str | None = None,
        brief: str | None = None,
    ) -> None:
        now = _now_iso()
        fields = ["messages_json = ?", "updated_at = ?"]
        params: list[Any] = [
            json.dumps(messages, ensure_ascii=False),
            now,
        ]
        if status is not None:
            fields.append("status = ?")
            params.append(status)
        if title is not None:
            fields.append("title = ?")
            params.append(title)
        if brief is not None:
            fields.append("brief = ?")
            params.append(brief)
        params.append(session_id)
        conn.execute(
            f"UPDATE chat_sessions SET {', '.join(fields)} WHERE id = ?",
            params,
        )

    def append_user_message(self, session_id: str, content: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Сессия не найдена: {session_id}")
        if session["status"] == STATUS_ANALYZED:
            raise ValueError("Сессия уже проанализирована.")
        messages = list(session["messages"])
        messages.append({"role": "user", "content": content.strip()})
        title = session["title"]
        if not title and content.strip():
            title = content.strip()[:120]
        with self._connect() as conn:
            self._save_messages(conn, session_id, messages, title=title)
            conn.commit()
        return self.get_session(session_id)

    def append_assistant_message(
        self,
        session_id: str,
        content: str,
        *,
        mark_ready: bool = False,
    ) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Сессия не найдена: {session_id}")
        cleaned, has_marker = _strip_marker(content)
        ready = mark_ready or has_marker
        messages = list(session["messages"])
        messages.append({"role": "assistant", "content": cleaned})
        status = STATUS_READY if ready else session["status"]
        brief = compile_interview_brief(messages) if ready else session.get("brief")
        with self._connect() as conn:
            self._save_messages(
                conn,
                session_id,
                messages,
                status=status,
                brief=brief,
            )
            conn.commit()
        return self.get_session(session_id)

    def save_messages_raw(self, session_id: str, messages: list[dict[str, str]]) -> None:
        """
        Сохраняет массив messages напрямую (включая служебные сообщения состояния).
        Используется для персистентности InterviewStateManager.
        """
        with self._connect() as conn:
            self._save_messages(conn, session_id, messages)
            conn.commit()

    def mark_ready(self, session_id: str) -> dict[str, Any]:
        """Принудительное завершение интервью (если модель не выставила маркер)."""
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Сессия не найдена: {session_id}")
        messages = session["messages"]
        brief = compile_interview_brief(messages)
        with self._connect() as conn:
            self._save_messages(
                conn,
                session_id,
                messages,
                status=STATUS_READY,
                brief=brief,
            )
            conn.commit()
        return self.get_session(session_id)

    def mark_analyzed(self, session_id: str, brief: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Сессия не найдена: {session_id}")
        with self._connect() as conn:
            self._save_messages(
                conn,
                session_id,
                session["messages"],
                status=STATUS_ANALYZED,
                brief=brief,
            )
            conn.commit()
        return self.get_session(session_id)
