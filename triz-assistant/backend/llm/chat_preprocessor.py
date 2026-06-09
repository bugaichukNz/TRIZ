"""
Препроцессор диалога ТРИЗ.

Извлекает структурированные данные из свободного текста пользователя
и инжектирует их в историю как системный контекст перед вызовом LLM.

Использование в chat():
    known = _extract_known_data(user_text, llm)
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Промпт извлечения — отдельный вызов LLM, только JSON, без рассуждений
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """Ты — строгий парсер данных для ТРИЗ-интервью.
Правило №1: извлекай ТОЛЬКО дословно сказанное.
Правило №2: если информация не присутствует явно в тексте — ставь null.
Правило №3: логические выводы, интерпретации и домысливание ЗАПРЕЩЕНЫ.
Верни строго валидный JSON без markdown и пояснений."""

_EXTRACT_USER = """Из текста ниже извлеки данные для ТРИЗ-интервью.

Верни JSON строго в этом формате (все поля обязательны, отсутствующие — null):
{{
  "ne_fact":           "конкретный физический/технологический факт НЭ или null",
  "ne_where":          "место НЭ: узел, зона, место в цепочке или null",
  "ne_when":           "условия/момент проявления НЭ — конкретные параметры (температура, давление, режим, тип шва и т.п.); НЕ просто 'в процессе работы' или 'при контроле' (тавтология) — иначе null",
  "consequences":      "последствия если не устранить или null",
  "cause_hypothesis":  "гипотеза причины НЭ — только если задачедатель явно её назвал; если не назвал явно — null",
  "constraints":       "жёсткие ограничения — что нельзя менять или null",
  "resources":         "доступные ресурсы: бюджет, люди, время или null",
  "known_solutions":   "предыдущие попытки решения или null",
  "expected_result":   "ожидаемый технический результат (желательно в числах) или null",
  "economic_result":   "ожидаемый экономический результат или null"
}}

Текст:
{text}"""


_VALIDATE_NE_WHEN_PROMPT = """Оцени, является ли текст ниже реальным ответом на вопрос
«при каких конкретных условиях проявляется нежелательный эффект» —
или это тавтология/перефраз самого вопроса.

Реальный ответ содержит конкретику: температуру, давление, режим работы,
тип соединения, периодичность, внешние условия и т.п.

Тавтология — это фразы вида «при проведении контроля», «в процессе УЗК»,
«при выполнении работ», «при контроле швов» и любые аналогичные.

Текст: "{value}"

Ответь строго одним словом: РЕАЛЬНЫЙ или ТАВТОЛОГИЯ"""


def _normalize_text(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _is_tautology_ne_when(value: str, llm) -> bool:
    try:
        response = llm.invoke(
            [HumanMessage(content=_VALIDATE_NE_WHEN_PROMPT.format(value=value))]
        )
        raw = response.content if hasattr(response, "content") else str(response)
        result = str(raw).strip().upper()
        return "ТАВТОЛОГИЯ" in result
    except Exception:
        # При ошибке валидации не сбрасываем значение.
        return False


def _postprocess_extracted_data(data: dict, source_text: str, llm) -> dict:
    """
    Пост-валидация извлечённых полей, чтобы убрать домысливания модели.
    """
    processed = dict(data)
    source_normalized = _normalize_text(source_text)

    ne_when = processed.get("ne_when")
    if isinstance(ne_when, str) and _is_tautology_ne_when(ne_when, llm):
        processed["ne_when"] = None

    cause_hypothesis = processed.get("cause_hypothesis")
    if isinstance(cause_hypothesis, str):
        cause_norm = _normalize_text(cause_hypothesis)
        # Если гипотеза не подтверждается текстом пользователя, считаем домысливанием.
        if not cause_norm or cause_norm not in source_normalized:
            processed["cause_hypothesis"] = None

    return processed


def _extract_known_data(user_messages_text: str, llm) -> dict:
    """
    Вызывает LLM для извлечения структурированных данных из истории сообщений.
    Возвращает dict с полями или пустой dict при ошибке.
    """
    try:
        prompt = [
            SystemMessage(content=_EXTRACT_SYSTEM),
            HumanMessage(content=_EXTRACT_USER.format(text=user_messages_text)),
        ]
        response = llm.invoke(prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        raw = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(raw)
        data = _postprocess_extracted_data(data, user_messages_text, llm)
        # Оставляем только непустые поля
        return {k: v for k, v in data.items() if v is not None}
    except Exception as exc:
        logger.warning("Препроцессор: не удалось извлечь данные: %s", exc)
        return {}


def _build_context_message(known: dict) -> str:
    """
    Формирует текст контекстного сообщения для инжекции в историю.
    """
    if not known:
        return ""

    FIELD_LABELS = {
        "ne_fact":          "НЭ (факт)",
        "ne_where":         "НЭ — где",
        "ne_when":          "НЭ — когда",
        "consequences":     "Последствия",
        "cause_hypothesis": "Гипотеза причины (со слов задачедателя)",
        "constraints":      "Ограничения",
        "resources":        "Ресурсы",
        "known_solutions":  "Известные решения/попытки",
        "expected_result":  "Ожидаемый технический результат",
        "economic_result":  "Ожидаемый экономический результат",
    }

    # Какие поля нужны для закрытия каждого блока
    BLOCK_REQUIRED = {
        "1 — НЭ":                    ["ne_fact", "ne_where", "ne_when", "consequences", "cause_hypothesis"],
        "2 — Система":               [],  # данных пока нет — блок открыт
        "3 — Результаты":            ["expected_result", "economic_result"],
        "4 — Ограничения/ресурсы":   ["constraints", "resources"],
        "5 — Известные решения":     ["known_solutions"],
    }

    lines = ["[КОНТЕКСТ: данные, уже полученные от задачедателя]"]
    for key, label in FIELD_LABELS.items():
        if key in known:
            lines.append(f"• {label}: {known[key]}")

    lines.append("")
    lines.append("[СТАТУС БЛОКОВ]")
    for block, required_fields in BLOCK_REQUIRED.items():
        if not required_fields:
            lines.append(f"• {block}: НЕ ЗАКРЫТ — данных не получено")
            continue
        missing = [f for f in required_fields if f not in known]
        if not missing:
            lines.append(f"• {block}: ЗАКРЫТ")
        else:
            missing_labels = [FIELD_LABELS[f] for f in missing]
            lines.append(f"• {block}: НЕ ЗАКРЫТ — отсутствуют: {', '.join(missing_labels)}")

    lines.append("")
    lines.append(
        "[ИНСТРУКЦИЯ: найди первый незакрытый блок. "
        "Внутри него — найди первое отсутствующее поле. "
        "Задай ОДИН вопрос именно по нему. "
        "Не переходи к следующему блоку пока текущий не закрыт.]"
    )
    return "\n".join(lines)


def preprocess_chat_history(
    messages: list[dict[str, str]],
    llm,
) -> list[dict[str, str]]:
    """
    Основная функция препроцессора.

    Алгоритм:
    1. Собирает все user-сообщения в один текст.
    2. Вызывает LLM для извлечения структурированных данных.
    3. Если данные найдены — инжектирует контекстное сообщение
       как последнее assistant-сообщение перед финальным user-сообщением.
       (Вставка именно перед последним user — модель видит контекст
        непосредственно перед тем, как формулирует следующий вопрос.)

    Не изменяет оригинальный список — возвращает новый.
    БД не затрагивается (вызывается только внутри chat() до сборки lc_messages).
    """
    if not messages:
        return messages

    # Собираем текст только из user-сообщений
    user_text_parts = [
        m["content"] for m in messages
        if m.get("role") == "user" and (m.get("content") or "").strip()
    ]
    if not user_text_parts:
        return messages

    combined_user_text = "\n\n".join(user_text_parts)

    # Извлекаем известные данные
    known = _extract_known_data(combined_user_text, llm)
    if not known:
        return messages

    context_text = _build_context_message(known)
    if not context_text:
        return messages

    logger.debug(
        "Препроцессор извлёк %d полей: %s",
        len(known),
        list(known.keys()),
    )

    # Инжектируем контекст: вставляем как assistant-сообщение
    # перед последним user-сообщением
    result = list(messages)
    insert_pos = len(result) - 1
    while insert_pos > 0 and result[insert_pos].get("role") != "user":
        insert_pos -= 1

    result.insert(insert_pos, {"role": "assistant", "content": context_text})
    return result
