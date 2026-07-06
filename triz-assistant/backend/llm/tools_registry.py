"""Реестр инструментов TRIZ core-анализа для профиля AnalysisProfile."""

from typing import Literal, TypedDict


class ToolRegistryEntry(TypedDict):
    title: str
    description: str
    category: Literal["базовый", "опциональный"]
    warning_if_disabled: str | None


TOOLS_REGISTRY: dict[str, ToolRegistryEntry] = {
    "tool_2_problem_statement": {
        "title": "Инструмент 2 — Постановка задачи",
        "description": "Формализация нежелательного эффекта и постановка задачи в терминах ТРИЗ.",
        "category": "базовый",
        "warning_if_disabled": (
            "Без постановки задачи анализ может опираться на неформализованное описание; "
            "риск неверной интерпретации НЭ."
        ),
    },
    "tool_14_ksa": {
        "title": "Инструмент 14 — КСА (компонентно-структурный анализ)",
        "description": "Модель системы: компоненты, связи, полезные и вредные функции.",
        "category": "базовый",
        "warning_if_disabled": (
            "Без КСА системная модель будет неполной; ресурсы и функции могут быть упущены."
        ),
    },
    "tool_11_psa": {
        "title": "Инструмент 11 — ПСА (причинно-следственный анализ)",
        "description": "Цепочка «почему?» до корневой физической причины.",
        "category": "базовый",
        "warning_if_disabled": (
            "Без ПСА корневая причина не будет верифицирована; решения могут лечить симптом."
        ),
    },
    "supfield_analysis": {
        "title": "Вепольный (Su-Field) анализ",
        "description": "Модель «субstance–поле» для выявления недостающих или вредных полей.",
        "category": "опциональный",
        "warning_if_disabled": None,
    },
    "contradiction_matrix": {
        "title": "Матрица противоречий (40 принципов)",
        "description": "Подбор изобретательских принципов по типовым параметрам.",
        "category": "опциональный",
        "warning_if_disabled": None,
    },
    "trimming": {
        "title": "Тримминг (упрощение системы)",
        "description": "Поиск избыточных компонентов и передача их функций другим элементам.",
        "category": "опциональный",
        "warning_if_disabled": None,
    },
}

# Ключи инструментов → метки для проверки _missing_mandatory_tools (chain.py).
TOOL_MANDATORY_MARKER_NAMES: dict[str, str] = {
    "tool_2_problem_statement": "Инструмент 2",
    "tool_14_ksa": "Инструмент 14 (КСА)",
    "tool_11_psa": "Инструмент 11 (ПСА)",
}

DEFAULT_TOOLS_ENABLED: dict[str, bool] = {
    key: entry["category"] == "базовый" for key, entry in TOOLS_REGISTRY.items()
}
