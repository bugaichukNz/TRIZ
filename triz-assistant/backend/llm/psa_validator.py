"""Валидация ПСА: root_cause не должен фиксироваться на отвергнутом костыле."""

from __future__ import annotations

import re

from backend.llm.fp_validator import _parse_fp_formula

_REJECTION_TRIGGERS: list[re.Pattern[str]] = [
    re.compile(r"\bбез\s+(?:использования\s+)?линз", re.IGNORECASE),
    re.compile(r"\bбез\s+линзов", re.IGNORECASE),
    re.compile(r"\bотказ(?:а)?\s+от\s+линз", re.IGNORECASE),
    re.compile(r"\bбез\s+([\w\-]+(?:\s+[\w\-]+){0,3})\b", re.IGNORECASE),
    re.compile(r"\bотказ(?:а)?\s+от\s+([\w\-]+(?:\s+[\w\-]+){0,4})", re.IGNORECASE),
]

_COMPONENT_STEM_MAP: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"линз", re.IGNORECASE), ["линз", "преломл", "фокусн", "аберрац"]),
    (re.compile(r"кле", re.IGNORECASE), ["кле", "адгез", "склеив"]),
    (re.compile(r"поднос", re.IGNORECASE), ["поднос"]),
]

def _collect_source_texts(core: dict) -> list[str]:
    ctx = core.get("system_context") or {}
    constraints = ctx.get("constraints") or []
    if not isinstance(constraints, list):
        constraints = [constraints] if constraints else []
    parts = [
        core.get("ideal_final_result", ""),
        core.get("known_solutions", ""),
        core.get("why_failed", ""),
        *constraints,
    ]
    return [str(p).strip() for p in parts if str(p).strip()]


def extract_rejected_component_stems(core: dict) -> list[str]:
    """Стебли слов, характеризующие отвергнутые в ИКР/constraints компоненты."""
    stems: set[str] = set()
    for text in _collect_source_texts(core):
        lowered = text.lower()
        for pattern, component_stems in _COMPONENT_STEM_MAP:
            if pattern.search(lowered):
                stems.update(component_stems)
        for trigger in _REJECTION_TRIGGERS[:3]:
            if trigger.search(lowered):
                for _, component_stems in _COMPONENT_STEM_MAP:
                    if component_stems[0] == "линз":
                        stems.update(component_stems)
        for trigger in _REJECTION_TRIGGERS[3:]:
            match = trigger.search(lowered)
            if not match:
                continue
            phrase = (match.group(1) or "").strip().lower()
            if not phrase or len(phrase) < 3:
                continue
            for pattern, component_stems in _COMPONENT_STEM_MAP:
                if pattern.search(phrase):
                    stems.update(component_stems)
                    break
            else:
                token = phrase.split()[0][:6]
                if len(token) >= 4:
                    stems.add(token)
    return sorted(stems)


def _find_forbidden_stem(text: str, stems: list[str]) -> str | None:
    lowered = (text or "").lower()
    if not lowered:
        return None
    for stem in stems:
        if stem in lowered:
            return stem
    return None


def validate_root_cause_not_crutch(core: dict) -> tuple[bool, str]:
    """
    root_cause и конец causal_chains не должны упоминать компонент,
    отвергнутый в ИКР/constraints (костыль текущего решения).
    """
    rejected_stems = extract_rejected_component_stems(core)
    if not rejected_stems:
        return True, ""

    root_cause = core.get("root_cause", "")
    hit = _find_forbidden_stem(root_cause, rejected_stems)
    if hit:
        return (
            False,
            f"root_cause зафиксирован на отвергнутом компоненте/костыле (найдено «{hit}»). "
            "ПСА должен докопаться до первичной причины: зачем вообще нужен этот компонент? "
            "Корень — геометрия/физика первичной проблемы (напр. пространственное разнесение "
            "источников и требование сведения в точку), а не дефект линз/клея/механизма.",
        )

    analysis = core.get("analysis") or {}
    chains = analysis.get("causal_chains", "")
    tail = chains
    if "корень" in chains.lower():
        tail = chains.lower().split("корень")[-1]
    elif "→" in chains:
        tail = chains.split("→")[-1]

    hit = _find_forbidden_stem(tail, rejected_stems)
    if hit:
        return (
            False,
            f"Цепочка ПСА заканчивается на отвергнутом компоненте (найдено «{hit}»). "
            "Продолжи «почему?» до первичной геометрической/физической причины, "
            "не останавливайся на недостатке текущего решения.",
        )

    return True, ""


def validate_fp_not_rejected_component(
    physical_contradiction: str,
    core: dict,
) -> tuple[bool, str]:
    """Параметр и элемент ФП не должны относиться к отвергнутому компоненту."""
    rejected_stems = extract_rejected_component_stems(core)
    if not rejected_stems:
        return True, ""

    fp = (physical_contradiction or "").strip()
    hit = _find_forbidden_stem(fp, rejected_stems)
    if hit:
        parsed = _parse_fp_formula(fp)
        element = parsed[0] if parsed else "—"
        parameter = parsed[1] if parsed else "—"
        return (
            False,
            f"ФП использует отвергнутый компонент (найдено «{hit}» в элементе «{element}» "
            f"или параметре «{parameter}»). ИКР/constraints исключают этот компонент — "
            "выбери параметр геометрии остающихся элементов (торец, зона сведения, "
            "взаимное расположение волокон), а не характеристику отвергнутого костыля.",
        )

    return True, ""


def validate_psa_and_fp_alignment(core: dict) -> tuple[bool, str]:
    """Сводная проверка ПСА + запрет параметра отвергнутого компонента в ФП."""
    parts: list[str] = []

    ok_rc, fb_rc = validate_root_cause_not_crutch(core)
    if not ok_rc:
        parts.append(fb_rc)

    ok_fp, fb_fp = validate_fp_not_rejected_component(
        core.get("physical_contradiction", ""),
        core,
    )
    if not ok_fp:
        parts.append(fb_fp)

    if parts:
        return False, "\n".join(parts)
    return True, ""
