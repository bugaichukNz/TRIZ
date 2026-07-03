from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_STATE_ROLE = "system"
_STATE_PREFIX = "__interview_state__:"
_CONTEXT_PREFIX = "[КОНТЕКСТ:"
_DIALOG_TAIL = 6
_SKIPPED_VALUE = "—"
_MAX_FIELD_ATTEMPTS = 2

_SKIP_MARKERS = (
    "не знаю",
    "не известно",
    "неизвестно",
    "нет данных",
    "затрудняюсь",
    "трудно сказать",
    "не могу сказать",
    "пропустить",
    "пропусти",
)


def _is_skip_answer(text: str) -> bool:
    t = text.strip().lower()
    return len(t) < 40 and any(m in t for m in _SKIP_MARKERS)

_RETRY_HINTS: dict[str, str] = {
    "ne_when": (
        "Предыдущий ответ отклонён (тавтология). Переспроси с уточнением: "
        "«Вы назвали процесс, а нужны конкретные условия: температура, режим, тип шва»."
    ),
}

_TIME_ONLY = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?\s*$")
_DATETIME_ONLY = re.compile(
    r"^\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2}(:\d{2})?\s*$"
)

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
            "attempts": {},
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
        state = self._empty_state()
        state_index = -1
        for i, msg in enumerate(messages):
            if self._is_state_message(msg):
                try:
                    raw = msg["content"][len(_STATE_PREFIX) :]
                    parsed = json.loads(raw)
                    if "pending_field" not in parsed:
                        parsed["pending_field"] = None
                    if "asked" not in parsed:
                        parsed["asked"] = []
                    if "confirmed" not in parsed:
                        parsed["confirmed"] = {}
                    if "attempts" not in parsed:
                        parsed["attempts"] = {}
                    state = parsed
                    state_index = i
                except Exception:
                    pass
        return state, state_index

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

    @property
    def confirmed(self) -> dict[str, str]:
        return dict(self._state.get("confirmed", {}))

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
        self._state.setdefault("attempts", {}).pop(field, None)
        logger.debug("Подтверждено поле (manual): %s", field)

    def mark_asked(self, field: str) -> None:
        if field not in self._state["asked"]:
            self._state["asked"].append(field)

    @staticmethod
    def _normalize_line(line: str) -> str:
        return " ".join(line.strip().split()).lower()

    @classmethod
    def _last_assistant_prompt(cls, messages: list[dict[str, str]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and not cls._is_context_message(msg):
                content = (msg.get("content") or "").strip()
                if content:
                    return content
        return ""

    @classmethod
    def sanitize_user_answer(
        cls,
        raw: str,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        """
        Убирает артефакты UI из ответа пользователя.

        Удаляются только:
        - строки, целиком являющиеся таймстемпом UI (15:37, 01.06.2026 15:37);
        - строки, полностью совпадающие с текстом последнего вопроса ассистента;
        - префикс, если ответ начинается с полного текста вопроса (копипаст).

        Соотношения (9:1, 12:1), числа и время внутри предложения НЕ трогаем.
        """
        text = (raw or "").strip()
        if not text:
            return ""

        assistant = cls._last_assistant_prompt(messages or []) if messages else ""
        assistant_lines: set[str] = set()
        if assistant:
            assistant_lines.add(cls._normalize_line(assistant))
            for line in assistant.splitlines():
                norm = cls._normalize_line(line)
                if len(norm) >= 12:
                    assistant_lines.add(norm)

        kept: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if _TIME_ONLY.match(stripped) or _DATETIME_ONLY.match(stripped):
                continue
            if cls._normalize_line(stripped) in assistant_lines:
                continue
            kept.append(stripped)

        result = "\n".join(kept).strip()
        if assistant and result.startswith(assistant):
            result = result[len(assistant) :].strip()
        elif assistant:
            a_norm = cls._normalize_line(assistant)
            r_norm = cls._normalize_line(result)
            if r_norm == a_norm:
                result = ""

        return result.strip()

    def _skip_stale_field(self, field: str) -> None:
        """Поле исчерпало лимит попыток — закрываем пропуском, чтобы не зациклиться."""
        self._state["confirmed"][field] = _SKIPPED_VALUE
        if field not in self._state["asked"]:
            self._state["asked"].append(field)
        self._state.setdefault("attempts", {}).pop(field, None)
        logger.info(
            "Поле %s пропущено после %d неудачных попыток",
            field,
            _MAX_FIELD_ATTEMPTS,
        )

    def _field_attempts(self, field: str) -> int:
        return int(self._state.get("attempts", {}).get(field, 0))

    def _bump_attempt(self, field: str) -> None:
        attempts = self._state.setdefault("attempts", {})
        attempts[field] = attempts.get(field, 0) + 1
        logger.debug(
            "Неудачная попытка для %s: %d/%d",
            field,
            attempts[field],
            _MAX_FIELD_ATTEMPTS,
        )

    def confirm_pending_answer(
        self,
        answer: str,
        *,
        reject_field: Callable[[str, str], bool] | None = None,
        messages: list[dict[str, str]] | None = None,
    ) -> bool:
        """Подтверждает ответ пользователя на поле pending_field. True — поле пропущено."""
        text = self.sanitize_user_answer(answer, messages)
        field = self._state.get("pending_field")

        if not field or field in self._state["confirmed"]:
            self._state["pending_field"] = None
            return False

        if not text:
            logger.debug("Пустой ответ после очистки для %s", field)
            self._bump_attempt(field)
            self._state["pending_field"] = None
            return False

        if _is_skip_answer(text):
            self._state["confirmed"][field] = _SKIPPED_VALUE
            if field not in self._state["asked"]:
                self._state["asked"].append(field)
            self._state.setdefault("attempts", {}).pop(field, None)
            self._state["pending_field"] = None
            logger.debug("Поле %s пропущено пользователем (отказ от ответа)", field)
            return True

        if reject_field and reject_field(field, text):
            logger.debug("Ответ на %s отклонён валидатором", field)
            self._bump_attempt(field)
            self._state["pending_field"] = None
            return False

        self.confirm_manual(field, text)
        self._state["pending_field"] = None
        return False

    def prepare_next_pending(self) -> None:
        """Выставляет pending_field на поле следующего вопроса (до вызова LLM)."""
        nxt = self.next_field_to_ask()
        if not nxt:
            self._state["pending_field"] = None
            return

        field = nxt[0]
        if field in self._state["asked"] and field not in self._state["confirmed"]:
            if self._field_attempts(field) >= _MAX_FIELD_ATTEMPTS:
                self._skip_stale_field(field)
                nxt = self.next_field_to_ask()
                if not nxt:
                    self._state["pending_field"] = None
                    return
                field = nxt[0]
            else:
                self._state["pending_field"] = field
                return

        self._state["pending_field"] = field
        self.mark_asked(field)

    @staticmethod
    def last_user_message(messages: list[dict[str, str]]) -> str:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                raw = (msg.get("content") or "").strip()
                if raw:
                    return InterviewStateManager.sanitize_user_answer(raw, messages)
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
        pending = self._state.get("pending_field")
        attempts = self._state.get("attempts", {})
        if next_field:
            field_key, field_label = next_field
            if (
                pending == field_key
                and field_key not in confirmed
                and attempts.get(field_key, 0) >= 1
            ):
                retry_hint = _RETRY_HINTS.get(
                    field_key,
                    "Задай уточняющий переспрос по тому же полю.",
                )
                lines.append(
                    f"[ИНСТРУКЦИЯ: переспрос поля «{field_label}». {retry_hint}]"
                )
            else:
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
