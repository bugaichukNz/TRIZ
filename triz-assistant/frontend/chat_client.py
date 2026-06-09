"""HTTP-клиент диалогового интервью TRIZ."""

from __future__ import annotations

import requests

CHAT_OPENING_MESSAGE = (
    "Добрый день. Прежде чем мы перейдём к анализу, мне нужно собрать исходные "
    "данные о задаче. Буду задавать вопросы по одному.\n"
    "Начнём с идентификации. Как кратко называется задача, которую нужно решить?"
)


def list_chat_sessions(base_url: str, *, limit: int = 20) -> list[dict]:
    response = requests.get(
        f"{base_url.rstrip('/')}/chat/sessions",
        params={"limit": limit},
        timeout=15,
    )
    _raise_for_status(response)
    return response.json().get("items", [])


def create_chat_session(base_url: str) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/sessions",
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def get_chat_session(base_url: str, session_id: str) -> dict:
    response = requests.get(
        f"{base_url.rstrip('/')}/chat/sessions/{session_id}",
        timeout=15,
    )
    _raise_for_status(response)
    return response.json()


def send_chat_message(base_url: str, session_id: str, content: str) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/sessions/{session_id}/messages",
        json={"content": content},
        timeout=120,
    )
    _raise_for_status(response)
    return response.json()


def complete_chat_session(base_url: str, session_id: str) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/sessions/{session_id}/complete",
        timeout=15,
    )
    _raise_for_status(response)
    return response.json()


def delete_chat_session(base_url: str, session_id: str) -> int:
    response = requests.delete(
        f"{base_url.rstrip('/')}/chat/sessions/{session_id}",
        timeout=15,
    )
    _raise_for_status(response)
    return int(response.json().get("deleted", 0))


def bulk_delete_chat_sessions(base_url: str, session_ids: list[str]) -> int:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/sessions/bulk-delete",
        json={"ids": session_ids},
        timeout=30,
    )
    _raise_for_status(response)
    return int(response.json().get("deleted", 0))


def delete_all_chat_sessions(base_url: str) -> int:
    response = requests.delete(
        f"{base_url.rstrip('/')}/chat/sessions",
        timeout=30,
    )
    _raise_for_status(response)
    return int(response.json().get("deleted", 0))


def analyze_chat_session(base_url: str, session_id: str) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}/chat/sessions/{session_id}/analyze",
        timeout=180,
    )
    _raise_for_status(response)
    return response.json()


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code < 400:
        return
    detail = response.text
    try:
        detail = response.json().get("detail", detail)
    except ValueError:
        pass
    raise requests.HTTPError(detail, response=response)
