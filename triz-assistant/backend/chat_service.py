"""Оркестрация диалогового интервью и запуска анализа."""

from __future__ import annotations

import logging

from backend.chat_brief import compile_interview_brief
from backend.chat_store import STATUS_ANALYZED, STATUS_READY, ChatStore
from backend.llm.chain import TRIZChain

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    """Ошибка чат-сервиса."""


class ChatService:
    def __init__(self, store: ChatStore, chain: TRIZChain) -> None:
        self._store = store
        self._chain = chain

    def create_session(self) -> dict:
        return self._store.create_session()

    def get_session(self, session_id: str) -> dict | None:
        return self._store.get_session(session_id)

    def send_message(self, session_id: str, content: str) -> dict:
        content = content.strip()
        if not content:
            raise ChatServiceError("Сообщение не может быть пустым.")

        session = self._store.get_session(session_id)
        if session is None:
            raise ChatServiceError("Сессия не найдена.")
        if session["status"] == STATUS_ANALYZED:
            raise ChatServiceError("Сессия уже проанализирована. Начните новый диалог.")
        if session["status"] == STATUS_READY:
            raise ChatServiceError(
                "Интервью завершено. Запустите TRIZ-анализ или начните новый диалог."
            )

        session = self._store.append_user_message(session_id, content)
        reply, updated_messages = self._chain.chat(session["messages"])
        self._store.save_messages_raw(session_id, updated_messages)
        session = self._store.append_assistant_message(session_id, reply)
        return session

    def complete_interview(self, session_id: str) -> dict:
        session = self._store.get_session(session_id)
        if session is None:
            raise ChatServiceError("Сессия не найдена.")
        if session["status"] == STATUS_ANALYZED:
            raise ChatServiceError("Сессия уже проанализирована.")
        return self._store.mark_ready(session_id)

    def analyze(self, session_id: str) -> tuple[dict, str]:
        session = self._store.get_session(session_id)
        if session is None:
            raise ChatServiceError("Сессия не найдена.")
        if session["status"] == STATUS_ANALYZED:
            raise ChatServiceError("Анализ для этой сессии уже выполнен.")

        if session["status"] != STATUS_READY:
            if len(session["messages"]) < 3:
                raise ChatServiceError(
                    "Недостаточно данных для анализа. Продолжите интервью."
                )
            session = self._store.mark_ready(session_id)

        brief = session.get("brief") or compile_interview_brief(session["messages"])
        if not brief.strip():
            raise ChatServiceError("Не удалось сформировать бриф интервью.")

        logger.info("TRIZ analyze from chat session %s, brief_len=%d", session_id, len(brief))
        result = self._chain.solve(brief)
        self._store.mark_analyzed(session_id, brief)
        return result, brief
