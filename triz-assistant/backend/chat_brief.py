"""Сборка брифа из истории интервью для POST /solve."""

from __future__ import annotations

from backend.llm.interview_state import (
    BLOCKS,
    FIELD_LABELS,
    InterviewStateManager,
    _SKIPPED_VALUE,
)

_GAPS_HEADER = "[ПРОБЕЛЫ В ДАННЫХ — не домысливать, пометить как assumption]"
_CONTEXT_PREFIX = "[КОНТЕКСТ:"

_FIELD_TO_TRIZ_INPUT = {
    "ne_fact": "Инструмент 2 (Постановка задачи) → целевой НЭ; Инструмент 11 (ПСА) → вход причинно-следственного анализа",
    "ne_where": "Инструмент 2 → оперативная зона (ОЗ); Инструмент 15 (Ресурсный анализ) → ОЗ",
    "ne_when": "Инструмент 2 → оперативное время (ОВ); Инструмент 15 → ОВ",
    "consequences": "Инструмент 11 (ПСА) → список НЭ; Инструмент 2 → список негативных эффектов",
    "cause_hypothesis": "Инструмент 11 (ПСА) → гипотезы о причинах НЭ (проверить в цепочках)",
    "system_function": "Инструмент 12 (ФА) → главная функция ТС; Инструмент 19 (ИКР) → ГПФ; Инструмент 26/27 → требуемое действие",
    "system_elements": "Инструмент 14 (КСА) → компонентная модель и структурная схема",
    "system_object": "Инструмент 12 (ФА) → объект функции; Инструмент 23 (Вепольный анализ) → В2",
    "supersystem": "Инструмент 5 (Системный оператор) → надсистема; Инструмент 14 → компоненты надсистемы",
    "expected_result": "Инструмент 19 (ИКР) → критерии идеальности; Инструмент 38 → целевые параметры",
    "economic_result": "Инструмент 38 (Экспертиза концепций) → экономические критерии отбора решений",
    "constraints": "Инструмент 2 → ограничения задачи; Инструмент 19 → ограничения на ИКР; Инструмент 25 (АРИЗ) → условия мини-задачи",
    "resources": "Инструмент 15 (Ресурсный анализ) → таблица ВПР; Инструмент 19 → ИКР-2 (только ВПР)",
    "known_solutions": "Инструмент 11 (ПСА) → способы решения ранее применённые; Инструмент 17 (Бенчмаркинг) → аналоги",
    "why_failed": "Инструмент 11 (ПСА) → почему предыдущие решения не сработали; Инструмент 2 → уточнение задачи",
    "unrealized_ideas": "Инструмент 8 (Копилка идей) → сырые идеи; Инструмент 29 (Задачи-аналоги) → нереализованные направления",
    "experts": "Инструмент 10 (Формирование команды) → эксперты предметной области",
}


def _ordered_confirmed(confirmed: dict[str, str]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    items: list[tuple[str, str]] = []
    for _, fields in BLOCKS:
        for field in fields:
            if field in confirmed:
                items.append((field, confirmed[field]))
                seen.add(field)
    for field, value in confirmed.items():
        if field not in seen:
            items.append((field, value))
    return items


def _is_skipped(value: str) -> bool:
    return (value or "").strip() == _SKIPPED_VALUE


def _append_confirmed_sections(lines: list[str], confirmed: dict[str, str]) -> None:
    if not confirmed:
        return

    data_lines: list[str] = []
    gap_lines: list[str] = []

    for field, value in _ordered_confirmed(confirmed):
        label = FIELD_LABELS.get(field, field)
        if _is_skipped(value):
            gap_lines.append(f"• {label}: данные не получены (пропущено в интервью)")
        else:
            data_lines.append(f"• {label}: {value.strip()}")
            triz_input = _FIELD_TO_TRIZ_INPUT.get(field, "")
            if triz_input:
                data_lines.append(f"  → {triz_input}")

    if data_lines:
        lines.append("## Подтверждённые данные (с привязкой к входам инструментов ТРИЗ)")
        lines.append("")
        lines.extend(data_lines)
        lines.append("")

    if gap_lines:
        lines.append(_GAPS_HEADER)
        lines.append("")
        lines.extend(gap_lines)
        lines.append("")


def _append_dialog(lines: list[str], messages: list[dict[str, str]]) -> None:
    dialog_added = False
    for msg in messages:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "system" and InterviewStateManager._is_state_message(msg):
            continue
        if role == "assistant" and content.startswith(_CONTEXT_PREFIX):
            continue
        if role == "user":
            if not dialog_added:
                lines.append("## Диалог (справочно)")
                lines.append("")
                dialog_added = True
            lines.append(f"### Задачедатель\n{content}\n")
        elif role == "assistant":
            if not dialog_added:
                lines.append("## Диалог (справочно)")
                lines.append("")
                dialog_added = True
            lines.append(f"### Аналитик\n{content}\n")


def compile_interview_brief(messages: list[dict[str, str]]) -> str:
    """Формирует текст задачи для экспертного анализа из диалога и состояния интервью."""
    lines = [
        "# Сводка интервью TRIZ (подтверждена задачедателем)",
        "",
    ]

    mgr = InterviewStateManager(messages)
    _append_confirmed_sections(lines, mgr.confirmed)
    _append_dialog(lines, messages)

    return "\n".join(lines).strip()
