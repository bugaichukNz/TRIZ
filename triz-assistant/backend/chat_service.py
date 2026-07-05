"""Оркестрация диалогового интервью и запуска анализа."""

from __future__ import annotations

import logging

from backend.analysis_progress import analysis_progress
from backend.chat_store import STATUS_ANALYZED, STATUS_INTERVIEW, STATUS_READY, ChatStore
from backend.llm.chain import TRIZChain, TRIZChainError
from backend.llm.interview_state import InterviewStateManager

logger = logging.getLogger(__name__)


class ChatServiceError(Exception):
    """Ошибка чат-сервиса."""


class ChatService:
    def __init__(self, store: ChatStore, chain: TRIZChain) -> None:
        self._store = store
        self._chain = chain

    def create_session(self, user_id: str) -> dict:
        return self._store.create_session(user_id)

    def get_session(self, session_id: str, user_id: str) -> dict | None:
        return self._store.get_session(session_id, user_id=user_id)

    def send_message(self, session_id: str, content: str, user_id: str) -> dict:
        content = content.strip()
        if not content:
            raise ChatServiceError("Сообщение не может быть пустым.")

        session = self._store.get_session(session_id, user_id=user_id)
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

    def complete_interview(self, session_id: str, user_id: str) -> dict:
        session = self._store.get_session(session_id, user_id=user_id)
        if session is None:
            raise ChatServiceError("Сессия не найдена.")
        if session["status"] == STATUS_ANALYZED:
            raise ChatServiceError("Сессия уже проанализирована.")
        return self._store.mark_ready(session_id)

    def prepare_analyze(
        self, session_id: str, user_id: str, *, force: bool = False
    ) -> tuple[str, object]:
        """Подготовка интервью к TRIZ-анализу: бриф и InterviewBrief."""
        session = self._store.get_session(session_id, user_id=user_id)
        if session is None:
            raise ChatServiceError("Сессия не найдена.")
        if session["status"] == STATUS_ANALYZED:
            raise ChatServiceError("Анализ для этой сессии уже выполнен.")

        if force and session["status"] == STATUS_INTERVIEW:
            has_user_reply = any(
                m.get("role") == "user" and (m.get("content") or "").strip()
                for m in session["messages"]
            )
            if not has_user_reply:
                raise ChatServiceError(
                    "Для принудительного анализа ответьте хотя бы на один вопрос."
                )
            session = self._store.mark_ready(session_id)
        elif session["status"] != STATUS_READY:
            if len(session["messages"]) < 3:
                raise ChatServiceError("Недостаточно данных для анализа. Продолжите интервью.")
            session = self._store.mark_ready(session_id)

        messages = session["messages"]
        interview_brief = InterviewStateManager(messages).export_brief()
        problem = session.get("brief") or interview_brief.to_prompt_text(messages)
        if not problem.strip():
            raise ChatServiceError("Не удалось сформировать бриф интервью.")

        return problem, interview_brief

    def analyze(self, session_id: str, user_id: str, *, force: bool = False) -> tuple[dict, str]:
        problem, interview_brief = self.prepare_analyze(session_id, user_id, force=force)

        logger.info(
            "TRIZ analyze from chat session %s, brief_len=%d",
            session_id,
            len(problem),
        )
        analysis_progress.start(session_id)

        def on_progress(pct: int, stage: str) -> None:
            analysis_progress.update(session_id, pct, stage)

        try:
            result = self._chain.solve(problem, brief=interview_brief, on_progress=on_progress)
            self._store.mark_analyzed(session_id, problem)
            analysis_progress.complete(session_id)
            return result, problem
        except TRIZChainError as exc:
            analysis_progress.fail(session_id, str(exc))
            raise
        except Exception as exc:
            analysis_progress.fail(session_id, str(exc))
            raise
