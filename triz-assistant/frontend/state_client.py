"""Клиент состояния UI в SQLite (через backend API)."""

from __future__ import annotations

import requests


def fetch_active_chat(base_url: str, *, timeout: float = 10) -> str | None:
    response = requests.get(
        f"{base_url.rstrip('/')}/state/active-chat",
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    session_id = data.get("session_id")
    return session_id if isinstance(session_id, str) and session_id else None


def save_active_chat(
    base_url: str,
    session_id: str | None,
    *,
    timeout: float = 10,
) -> None:
    response = requests.put(
        f"{base_url.rstrip('/')}/state/active-chat",
        json={"session_id": session_id},
        timeout=timeout,
    )
    response.raise_for_status()
