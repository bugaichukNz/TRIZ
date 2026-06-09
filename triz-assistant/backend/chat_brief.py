"""Сборка брифа из истории интервью для POST /solve."""

from __future__ import annotations


def compile_interview_brief(messages: list[dict[str, str]]) -> str:
    """Формирует текст задачи для экспертного анализа из диалога."""
    lines = [
        "# Сводка интервью TRIZ (подтверждена задачедателем)",
        "",
    ]
    for msg in messages:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"## Задачедатель\n{content}\n")
        elif role == "assistant":
            lines.append(f"## Аналитик\n{content}\n")
    return "\n".join(lines).strip()
