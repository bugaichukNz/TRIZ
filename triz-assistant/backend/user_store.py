"""SQLite-хранилище пользователей."""

from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.sessions_store import resolve_db_path

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "user"
DEFAULT_PASSWORD = "user"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    )
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected = stored_hash.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    )
    return secrets.compare_digest(digest.hex(), expected)


class UserStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or resolve_db_path()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_once(self) -> None:
        if self._initialized:
            return
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._seed_default_user(conn)
            conn.commit()
        self._initialized = True

    def _seed_default_user(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (DEFAULT_USERNAME,),
        ).fetchone()
        if row is not None:
            self._migrate_orphan_data(conn, row["id"])
            return
        user_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO users (id, username, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                DEFAULT_USERNAME,
                hash_password(DEFAULT_PASSWORD),
                _now_iso(),
            ),
        )
        logger.info("Создан пользователь по умолчанию: %s", DEFAULT_USERNAME)
        self._migrate_orphan_data(conn, user_id)

    def _migrate_orphan_data(self, conn: sqlite3.Connection, user_id: str) -> None:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        def _has_column(table: str, column: str) -> bool:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            return column in cols

        if "chat_sessions" in tables and _has_column("chat_sessions", "user_id"):
            conn.execute(
                "UPDATE chat_sessions SET user_id = ? WHERE user_id IS NULL",
                (user_id,),
            )
        if "history_entries" in tables and _has_column("history_entries", "user_id"):
            conn.execute(
                "UPDATE history_entries SET user_id = ? WHERE user_id IS NULL",
                (user_id,),
            )

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        self._init_once()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "password_hash": row["password_hash"],
            "created_at": row["created_at"],
        }

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        self._init_once()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, created_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "created_at": row["created_at"],
        }

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        user = self.get_by_username(username)
        if user is None:
            return None
        if not verify_password(password, user["password_hash"]):
            return None
        return {
            "id": user["id"],
            "username": user["username"],
            "created_at": user["created_at"],
        }


def active_chat_key(user_id: str) -> str:
    return f"active_chat_session_id:{user_id}"
