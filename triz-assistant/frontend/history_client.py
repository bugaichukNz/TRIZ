"""Клиент API истории TRIZ-отчётов (данные только в SQLite на backend)."""

from __future__ import annotations

from typing import Any

import requests

SESSIONS_ENDPOINT = "/sessions"


def fetch_history(
    base_url: str,
    *,
    limit: int = 20,
    summary: bool = True,
    timeout: float = 10,
) -> list[dict[str, Any]]:
    """Загружает историю отчётов из базы (summary — без тяжёлого result)."""
    response = requests.get(
        f"{base_url.rstrip('/')}{SESSIONS_ENDPOINT}",
        params={"limit": limit, "summary": summary},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return [_entry_to_ui(item) for item in data.get("items", [])]


def fetch_history_entry(
    base_url: str,
    entry_id: str,
    *,
    timeout: float = 15,
) -> dict[str, Any]:
    """Загружает одну запись истории с полным TRIZ-отчётом."""
    response = requests.get(
        f"{base_url.rstrip('/')}{SESSIONS_ENDPOINT}/{entry_id}",
        timeout=timeout,
    )
    response.raise_for_status()
    return _entry_to_ui(response.json())


def push_history_entry(
    base_url: str,
    problem: str,
    result: dict[str, Any],
    *,
    time_display: str | None = None,
    timeout: float = 30,
) -> dict[str, Any]:
    """Сохраняет запись в SQLite (если ещё не сохранена на backend)."""
    payload: dict[str, Any] = {"problem": problem, "result": result}
    if time_display:
        payload["time"] = time_display
    response = requests.post(
        f"{base_url.rstrip('/')}{SESSIONS_ENDPOINT}",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return _entry_to_ui(response.json())


def clear_history_api(base_url: str, *, timeout: float = 10) -> None:
    """Очищает историю отчётов в базе данных."""
    response = requests.delete(
        f"{base_url.rstrip('/')}{SESSIONS_ENDPOINT}",
        timeout=timeout,
    )
    response.raise_for_status()


def _entry_to_ui(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id", ""),
        "problem": entry["problem"],
        "result": entry["result"],
        "time": entry["time"],
        "created_at": entry.get("created_at"),
        "chat_session_id": entry.get("chat_session_id"),
    }
