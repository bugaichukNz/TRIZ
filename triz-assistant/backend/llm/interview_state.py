from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

_STATE_ROLE = "system"
_STATE_PREFIX = "__interview_state__:"
_CONTEXT_PREFIX = "[КОНТЕКСТ:"
_DIALOG_TAIL = 6

BLOCKS: list[tuple[str, list[str]]] = [
    ("1 — НЭ", ["ne_fact", "ne_where", "ne_when", "consequences", "cause_hypothesis"]),
    ("2 — Система", ["system_function", "system_elements", "system_object", "supersystem"]),
    ("3 — Результаты", ["expected_result", "economic_result"]),
    ("4 — Ограничения/ресурсы", ["constraints", "resources"]),
    ("5 — Известные решения", ["known_solutions", "why_failed", "unrealized_ideas"]),
    ("6 — Эксперты", ["experts"]),
]

FIELD_LABELS: dict[str, str] = {
    "ne_fact": "НЭ (факт)",
    "ne_where": "НЭ — где",
    "ne_when": "НЭ — когда",
    "consequences": "Последствия",
    "cause_hypothesis": "Гипотеза причины (явно названная задачедателем)",
    "system_function": "Главная функция системы",
    "system_elements": "Основные элементы системы",
    "system_object": "Объект обработки",
    "supersystem": "Надсистема",
    "expected_result": "Ожидаемый технический результат (в числах)",
    "economic_result": "Ожидаемый экономический результат",
    "constraints": "Жёсткие ограничения",
    "resources": "Доступные ресурсы",
    "known_solutions": "Известные попытки решения",
    "why_failed": "Почему не сработало",
    "unrealized_ideas": "Нереализованные идеи",
    "experts": "Эксперты (ФИО, должность)",
}

_AUTO_CONFIRMABLE = {
    "ne_fact",
    "ne_where",
    "consequences",
    "economic_result",
}

_MANUAL_ONLY = {
    "ne_when",
    "cause_hypothesis",
    "expected_result",
    "constraints",
    "resources",
    "known_solutions",
    "why_failed",
    "unrealized_ideas",
    "experts",
    "system_function",
    "system_elements",
    "system_object",
    "supersystem",
}


class InterviewStateManager:
    """
    Состояние интервью в messages (role=system, __interview_state__:JSON).
    Контекст для LLM собирается на лету через build_payload_messages и не пишется в БД.
    """

    def __init__(self, messages: list[dict[str, str]]) -> None:
        self._state, self._state_index = self._load(messages)

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "confirmed": {},
            "pending_field": None,
            "asked": [],
        }

    @staticmethod
    def _is_state_message(msg: dict[str, str]) -> bool:
        return (
            msg.get("role") == _STATE_ROLE
            and (msg.get("content") or "").startswith(_STATE_PREFIX)
        )

    @staticmethod
    def _is_context_message(msg: dict[str, str]) -> bool:
        return (
            msg.get("role") == "assistant"
            and (msg.get("content") or "").startswith(_CONTEXT_PREFIX)
        )

    def _load(self, messages: list[dict[str, str]]) -> tuple[dict[str, Any], int]:
        for i, msg in enumerate(messages):
            if self._is_state_message(msg):
                try:
                    raw = msg["content"][len(_STATE_PREFIX) :]
                    state = json.loads(raw)
                    if "pending_field" not in state:
                        state["pending_field"] = None
                    if "asked" not in state:
                        state["asked"] = []
                    if "confirmed" not in state:
                        state["confirmed"] = {}
                    return state, i
                except Exception:
                    pass
        return self._empty_state(), -1

    def _serialize(self) -> str:
        return _STATE_PREFIX + json.dumps(self._state, ensure_ascii=False)

    def inject_state(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Обновляет служебное сообщение состояния в конце списка."""
        result = [m for m in messages if not self._is_state_message(m)]
        result.append({"role": _STATE_ROLE, "content": self._serialize()})
        return result

    @property
    def pending_field(self) -> str | None:
        return self._state.get("pending_field")

    def set_pending_field(self, field: str | None) -> None:
        self._state["pending_field"] = field

    def confirm_from_extraction(self, known: dict[str, str]) -> None:
        for field, value in known.items():
            if field in _AUTO_CONFIRMABLE and field not in self._state["confirmed"]:
                self._state["confirmed"][field] = value
                logger.debug("Автоподтверждено поле: %s", field)

    def confirm_manual(self, field: str, value: str) -> None:
        self._state["confirmed"][field] = value.strip()
        if field not in self._state["asked"]:
            self._state["asked"].append(field)
        logger.debug("Подтверждено поле (manual): %s", field)

    def mark_asked(self, field: str) -> None:
        if field not in self._state["asked"]:
            self._state["asked"].append(field)

    def confirm_pending_answer(
        self,
        answer: str,
        *,
        reject_field: Callable[[str, str], bool] | None = None,
    ) -> None:
        """Подтверждает ответ пользователя на поле pending_field."""
        text = (answer or "").strip()
        if not text:
            return

        field = self._state.get("pending_field")

        if not field or field in self._state["confirmed"]:
            self._state["pending_field"] = None
            return

        if reject_field and reject_field(field, text):
            logger.debug("Ответ на %s отклонён валидатором", field)
            self._state["pending_field"] = None
            return

        self.confirm_manual(field, text)
        self._state["pending_field"] = None

    def prepare_next_pending(self) -> None:
        """Выставляет pending_field на поле следующего вопроса (до вызова LLM)."""
        nxt = self.next_field_to_ask()
        self._state["pending_field"] = nxt[0] if nxt else None
        if nxt:
            self.mark_asked(nxt[0])

    @staticmethod
    def last_user_message(messages: list[dict[str, str]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return (msg.get("content") or "").strip()
        return ""

    def get_status(self) -> list[dict[str, Any]]:
        confirmed = self._state["confirmed"]
        result = []
        for block_name, fields in BLOCKS:
            missing = [f for f in fields if f not in confirmed]
            result.append(
                {
                    "block": block_name,
                    "closed": len(missing) == 0,
                    "missing_fields": missing,
                    "missing_labels": [FIELD_LABELS[f] for f in missing],
                }
            )
        return result

    def first_open_block(self) -> dict[str, Any] | None:
        for block in self.get_status():
            if not block["closed"]:
                return block
        return None

    def next_field_to_ask(self) -> tuple[str, str] | None:
        block = self.first_open_block()
        if not block:
            return None
        for field in block["missing_fields"]:
            return field, FIELD_LABELS[field]
        return None

    def is_complete(self) -> bool:
        status = self.get_status()
        return all(b["closed"] for b in status[:-1])

    def build_context_message(self) -> str:
        confirmed = self._state["confirmed"]
        status = self.get_status()
        next_field = self.next_field_to_ask()

        lines: list[str] = []

        if confirmed:
            lines.append("[КОНТЕКСТ: данные, подтверждённые задачедателем]")
            for field, value in confirmed.items():
                label = FIELD_LABELS.get(field, field)
                lines.append(f"• {label}: {value}")
            lines.append("")

        lines.append("[СТАТУС БЛОКОВ]")
        for block in status:
            if block["closed"]:
                lines.append(f"• {block['block']}: ЗАКРЫТ")
            else:
                missing_str = ", ".join(block["missing_labels"])
                lines.append(f"• {block['block']}: НЕ ЗАКРЫТ — ожидаются: {missing_str}")

        lines.append("")
        if next_field:
            _, field_label = next_field
            lines.append(
                f"[ИНСТРУКЦИЯ: следующее поле для вопроса — «{field_label}». "
                f"Задай ОДИН конкретный вопрос именно по нему. "
                f"Не переходи к другим полям.]"
            )
        elif self.is_complete():
            lines.append(
                "[ИНСТРУКЦИЯ: все блоки 0–5 закрыты. "
                "Сделай резюме собранных данных и спроси подтверждение.]"
            )

        return "\n".join(lines)

    def _strip_ephemeral(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        return [
            m
            for m in messages
            if not self._is_state_message(m) and not self._is_context_message(m)
        ]

    def _trim_dialog_tail(self, dialog: list[dict[str, str]]) -> list[dict[str, str]]:
        if len(dialog) <= _DIALOG_TAIL:
            return dialog
        opening = dialog[0] if dialog and dialog[0].get("role") == "assistant" else None
        tail_len = _DIALOG_TAIL - (1 if opening else 0)
        tail = dialog[-tail_len:] if tail_len > 0 else []
        if opening and opening not in tail:
            return [opening, *tail]
        return tail

    def build_payload_messages(
        self,
        messages: list[dict[str, str]],
        context: str,
    ) -> list[dict[str, str]]:
        """
        Собирает messages для LLM: короткий хвост диалога + свежий контекст.
        Служебное состояние и старые [КОНТЕКСТ:...] не попадают в payload.
        """
        dialog = self._trim_dialog_tail(self._strip_ephemeral(messages))

        # Длинные user-сообщения заменяем заглушкой.
        # LLM не должна извлекать данные из свободного текста —
        # только из блока [КОНТЕКСТ: данные, подтверждённые задачедателем].
        cleaned = []
        for m in dialog:
            if m.get("role") == "user" and len(m.get("content", "")) > 200:
                cleaned.append({"role": "user", "content": "[данные переданы в блок КОНТЕКСТ]"})
            else:
                cleaned.append(m)
        dialog = cleaned

        if not context:
            return dialog

        insert_pos = len(dialog)
        for i in range(len(dialog) - 1, -1, -1):
            if dialog[i].get("role") == "user":
                insert_pos = i
                break

        result = list(dialog)
        result.insert(insert_pos, {"role": "assistant", "content": context})
        return result
