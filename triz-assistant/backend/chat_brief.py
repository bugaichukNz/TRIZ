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

    if data_lines:
        lines.append("## Подтверждённые данные")
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
