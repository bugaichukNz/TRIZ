"""Валидация сгенерированных концепций решений TRIZ."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MIN_SOLUTIONS = 2
MAX_SOLUTION_GENERATION_ATTEMPTS = 3
MIN_DISTINCT_APPROACHES = 3
PARTIAL_GENERATION_WARNING = (
    "часть решений не удалось сгенерировать в рамках ограничений — "
    "возможно, ограничения слишком жёсткие для данной задачи"
)

_VALIDATE_SYSTEM = """Ты — методический эксперт ТРИЗ. Проверяешь набор концепций решений по строгому чек-листу.
Не оценивай «в целом хорошо ли» — проверяй КАЖДОЕ решение по пунктам ниже.
Семантическое сравнение: «добавить датчик» и «установить сенсор» — одна категория.
Все формулировки feedback — на русском языке."""

_VALIDATE_USER = """Идеальный конечный результат (ИКР):
{ifr}

Доступные ресурсы (resources):
{resources}

Известные попытки решения (тупики — нельзя повторять семантически):
{known_solutions}

Почему не сработало (тупики — нельзя повторять семантически):
{why_failed}

Концепции решений для проверки:
{solutions_json}

Чек-лист для КАЖДОГО решения (все три пункта обязательны):

1. not_dead_end_duplicate — решение НЕ дублирует семантически КОНКРЕТНЫЙ тупик из known_solutions или why_failed
   (та же категория подхода: тот же принцип действия, та же идея в другой формулировке).
   known_solutions/why_failed — это перечисленные в брифе попытки, а НЕ описание задачи целиком.
   Тематическая близость к проблеме ≠ дубликат. Новый механизм в другой категории — НЕ дубликат,
   даже если решает ту же НЭ.

2. uses_specific_resource — решение явно опирается на конкретный ресурс из блока resources
   (вещественный / энергетический / пространственный / функциональный), указанный в mechanism или title.
   Достаточно одного конкретного ресурса из списка; общие слова без привязки — провал.

3. advances_ifr — решение приближает к ИКР
   (элемент САМ выполняет функцию / устраняет противоречие без лишних компонентов,
   либо в applicability явно показана связь с ИКР).

Верни passed=true если не менее {min_solutions} решений проходят ВСЕ три пункта.
Остальные решения с нарушениями перечисли в feedback, но не блокируй passed из-за них."""

_CONSTRAINT_SYSTEM = """Ты — методический эксперт ТРИЗ. Проверяешь, нарушает ли концепция решения ЖЁСТКИЕ ограничения из брифа.

Ключевой вопрос для КАЖДОГО решения:
«Потребует ли это решение, ПРЯМО или КОСВЕННО, нарушить хотя бы одно ограничение из constraints?»

Прямое нарушение: решение явно делает запрещённое
(«сменить материал катетера», «заменить стаканы на одноразовые», «установить новое оборудование»).

Косвенное нарушение: решение формулируется обходным путём, но для реализации ВЫНУЖДЕННО потребует запрещённого:
• «разработать новый катетер» / «новое изделие» при запрете менять материал катетера
  → новое изделие почти наверняка подразумевает новый материал, конструкцию или сертификацию → HARD FAIL;
• «новая конструкция подноса» при запрете менять поднос → HARD FAIL;
• «разработка нового покрытия» при запрете менять материал → HARD FAIL.

Допустимо (НЕ нарушение):
• доработка СУЩЕСТВУЮЩЕГО изделия в рамках того же материала и сертификации
  (только геометрия отверстий, режим эксплуатации, насадки на стандартный катетер);
• высокая стоимость/сложность В ПРЕДЕЛАХ ограничений — soft penalty, не отбраковка.

Если решение помечено «требует новых ресурсов» и это противоречит constraints — violates_constraint=true.
Все формулировки — на русском языке."""

_CONSTRAINT_USER = """Жёсткие ограничения (constraints) из брифа:
{constraints}

Концепции решений для проверки:
{solutions_json}

Для КАЖДОГО решения ответь на вопрос:
«Потребует ли это решение, прямо или косвенно, нарушить хотя бы одно ограничение из constraints?»

violates_constraint=true при ПРЯМОМ или КОСВЕННОМ нарушении.
Примеры косвенного нарушения:
• «разработка нового катетера с отверстиями» при «нельзя менять материал катетера»
  → новое изделие = новый материал/конструкция/сертификация;
• «новая конструкция X» при запрете менять X.

violates_constraint=false, если решение укладывается в существующее изделие/процесс
(насадка на стандартный катетер, изменение режима, геометрия без нового изделия).

В violated_constraint укажи текст нарушенного ограничения; в reason — цепочку:
что предлагает решение → что для этого неизбежно потребуется → какое ограничение нарушится."""

# Эвристика: «только расходники / без оборудования» vs установка автоматизированной системы.
_CONSUMABLES_ONLY_MARKERS = (
    "только расходник",
    "простые приспособлен",
    "не покупать",
    "без оборудован",
    "без нового оборудован",
)
_EQUIPMENT_SOLUTION_MARKERS = (
    "автоматизирован",
    "автоматическая систем",
    "автоматизированная систем",
    "новое оборудован",
    "установк",
    "станци",
    "комплекс суш",
    "система суш",
)

_MATERIAL_CHANGE_FORBIDDEN_MARKERS = (
    "нельзя менять материал",
    "нельзя менять базовый материал",
    "не менять материал",
    "не менять базовый материал",
    "запрещено менять материал",
    "запрещено изменять материал",
)
_NEW_PRODUCT_MARKERS = (
    "новый катетер",
    "нового катетер",
    "новое изделие",
    "нового изделия",
    "новый продукт",
    "нового продукта",
    "разработка нового",
    "разработать новый",
    "разработать новое",
    "разработка катетер",
    "новая конструкция катетер",
    "многофункциональн",
)

_PRINCIPLE_NUMBER_RE = re.compile(r"№\s*(\d+)", re.IGNORECASE)

# Стемы для эвристики «схлопывания» в одну категорию механизма.
_MECHANISM_CLUSTER_STEMS: tuple[str, ...] = (
    "силикон",
    "вкладыш",
    "вклад",
    "подклад",
    "прорезин",
    "гнёзд",
    "гнезд",
    "канавк",
    "салфет",
    "впитыва",
    "обдув",
    "сушк",
    "текстур",
    "наклон",
    "уклон",
    "желоб",
    "дренаж",
    "порист",
    "гидрофоб",
    "водооттал",
)

_DIVERSITY_SYSTEM = """Ты — методический эксперт ТРИЗ. Проверяешь РАЗНООБРАЗИЕ набора концепций решений.
Семантическое сравнение: «силиконовая подкладка», «силиконовый вкладыш» и «formный вкладыш» — одна категория механизма.
Все формулировки feedback — на русском языке."""

_DIVERSITY_USER = """Доступные ресурсы (resources):
{resources}

Концепции решений:
{solutions_json}

Проверка разнообразия набора (passed=true только если ВСЕ пункты выполнены):

1. distinct_principles — решения опираются на РАЗНЫЕ ТРИЗ-принципы (разные № или принципиально разные инструменты).
   Два решения с одним №, но разным механизмом — всё равно провал, если механизм тот же.

2. distinct_mechanisms — решения используют РАЗНЫЕ механизмы/ресурсы, а не вариации одной идеи
   (например, три вида силиконовых подкладок — провал).

3. resolution_axes — набор покрывает минимум 3 разные оси разрешения ФП среди:
   время (фазы процесса), пространство (зоны без маскировки «внутри/снаружи»),
   структура (форма/свойства элемента), надсистема (ресурсы зала/линии/кухни).

При passed=false в feedback:
- назови схлопнувшийся кластер (collapsed_cluster);
- перечисли, какие оси разрешения ФП не представлены;
- потребуй замены на разных принципах (время / пространство / структура / надсистема)."""


class _SolutionItemCheck(BaseModel):
    solution_id: int
    not_dead_end_duplicate: bool
    uses_specific_resource: bool
    advances_ifr: bool


class _SolutionChecklistResult(BaseModel):
    passed: bool
    feedback: str = Field(description="Что не так; пустая строка если passed=true")
    items: list[_SolutionItemCheck] = Field(default_factory=list)


class _ConstraintItemCheck(BaseModel):
    solution_id: int
    violates_constraint: bool
    violated_constraint: str = Field(
        default="", description="Текст нарушенного ограничения; пусто если нет нарушения"
    )
    reason: str = Field(default="", description="Почему решение нарушает ограничение")


class _ConstraintCheckResult(BaseModel):
    items: list[_ConstraintItemCheck] = Field(default_factory=list)


class _DiversityCheckResult(BaseModel):
    passed: bool
    distinct_principles: bool
    distinct_mechanisms: bool
    resolution_axes: bool
    collapsed_cluster: str = Field(
        default="",
        description="Кластер, в который схлопнулся набор; пусто если passed=true",
    )
    missing_axes: list[str] = Field(
        default_factory=list,
        description="Оси разрешения ФП, не представленные в наборе",
    )
    feedback: str = Field(description="Что исправить; пустая строка если passed=true")


def _format_solutions_for_prompt(solutions: list[dict]) -> str:
    return json.dumps(solutions, ensure_ascii=False, indent=2)


def _solution_score(solution: dict) -> float:
    return round(
        solution.get("effectiveness_score", 0)
        + solution.get("scalability_score", 0)
        - (solution.get("complexity_score", 0) + solution.get("cost_score", 0)) / 2,
        1,
    )


def _solution_dedup_key(solution: dict) -> str:
    title = (solution.get("title") or "").strip().lower()
    mechanism = (solution.get("mechanism") or "").strip().lower()[:80]
    return f"{title}|{mechanism}"


def merge_valid_solutions(*batches: list[dict]) -> list[dict]:
    """Объединяет валидные решения из нескольких попыток генерации (дедуп по title+mechanism)."""
    by_key: dict[str, dict] = {}
    for batch in batches:
        for sol in batch:
            key = _solution_dedup_key(sol)
            if not key.strip("|"):
                continue
            if key not in by_key or _solution_score(sol) > _solution_score(by_key[key]):
                by_key[key] = dict(sol)

    merged = sorted(by_key.values(), key=_solution_score, reverse=True)
    for index, sol in enumerate(merged, start=1):
        sol["id"] = index
    return merged


def _principle_key(solution: dict) -> str:
    principle = (solution.get("triz_principle") or "").strip()
    match = _PRINCIPLE_NUMBER_RE.search(principle)
    if match:
        return f"#{match.group(1)}"
    normalized = principle.lower()
    for prefix in ("принцип", "стандарт", "приём", "прием"):
        if prefix in normalized:
            return normalized[:60]
    return normalized[:60] or "unknown"


def _mechanism_cluster_hits(solution: dict) -> set[str]:
    text = _solution_text(solution)
    return {stem for stem in _MECHANISM_CLUSTER_STEMS if stem in text}


def _dominant_mechanism_clusters(
    solutions: list[dict],
) -> list[tuple[str, int, list[int]]]:
    """Стем → (число решений, id решений)."""
    stem_to_ids: dict[str, list[int]] = {}
    for sol in solutions:
        sid = sol.get("id")
        for stem in _mechanism_cluster_hits(sol):
            stem_to_ids.setdefault(stem, [])
            if sid is not None and int(sid) not in stem_to_ids[stem]:
                stem_to_ids[stem].append(int(sid))

    clusters = [(stem, len(ids), ids) for stem, ids in stem_to_ids.items() if len(ids) >= 2]
    clusters.sort(key=lambda item: item[1], reverse=True)
    return clusters


def _format_diversity_feedback(
    *,
    issues: list[str],
    clusters: list[tuple[str, int, list[int]]],
    principles: list[str],
) -> str:
    cluster_text = ""
    if clusters:
        stem, count, ids = clusters[0]
        cluster_text = f"кластер «{stem}» ({count} реш.: {', '.join(f'#{i}' for i in ids)})"

    issue_text = "; ".join(issues)
    if cluster_text and cluster_text not in issue_text:
        issue_text = f"{issue_text}; {cluster_text}" if issue_text else cluster_text

    principle_list = ", ".join(sorted(set(principles))) or "—"
    return (
        f"Набор решений недостаточно разнообразен: {issue_text}.\n"
        "Не повторяй вариации одной идеи (например, несколько видов силиконовых подкладок).\n"
        "Сгенерируй замены на РАЗНЫХ принципах разрешения ФП:\n"
        "• во времени — развести требования по фазам процесса;\n"
        "• в пространстве — разные зоны/элементы (без маскировки «внутри/снаружи»);\n"
        "• в структуре — изменение конструкции или свойств элемента;\n"
        "• в надсистеме — ресурсы и функции надсистемы (зал, линия выдачи, кухня).\n"
        f"Уже использованные принципы: {principle_list}. "
        "Каждое новое решение — другой ТРИЗ-принцип № и другой ключевой ресурс из resources."
    )


def _heuristic_diversity_check(solutions: list[dict]) -> tuple[bool, str]:
    if len(solutions) < 2:
        return True, ""

    required = min(MIN_DISTINCT_APPROACHES, len(solutions))
    principles = [_principle_key(sol) for sol in solutions]
    unique_principles = len(set(principles))
    clusters = _dominant_mechanism_clusters(solutions)

    issues: list[str] = []
    if len(solutions) >= 3 and unique_principles < required:
        issues.append(
            f"только {unique_principles} разных ТРИЗ-принципов при {len(solutions)} решениях "
            f"(нужно минимум {required})"
        )

    for stem, count, ids in clusters:
        if count >= 3:
            issues.append(
                f"{count} решений в одном механизме «{stem}» ({', '.join(f'#{i}' for i in ids)})"
            )
        elif count >= len(solutions) and len(solutions) >= 2:
            issues.append(f"все решения в механизме «{stem}»")

    principle_counts = Counter(principles)
    dup_principles = [p for p, c in principle_counts.items() if c >= 2]
    if dup_principles and len(solutions) >= 3:
        issues.append("повторяются ТРИЗ-принципы: " + ", ".join(sorted(dup_principles)))

    if issues:
        return False, _format_diversity_feedback(
            issues=issues, clusters=clusters, principles=principles
        )
    return True, ""


def _llm_diversity_check(
    solutions: list[dict],
    resources: str,
    llm,
) -> _DiversityCheckResult:
    structured = llm.with_structured_output(_DiversityCheckResult)
    return structured.invoke(
        [
            SystemMessage(content=_DIVERSITY_SYSTEM),
            HumanMessage(
                content=_DIVERSITY_USER.format(
                    resources=resources or "—",
                    solutions_json=_format_solutions_for_prompt(solutions),
                )
            ),
        ]
    )


def check_solution_diversity(
    solutions: list[dict],
    resources: str,
    llm,
) -> tuple[bool, str]:
    """
    Проверяет разнообразие набора: разные ТРИЗ-принципы и механизмы, не вариации одной идеи.
    """
    ok, feedback = _heuristic_diversity_check(solutions)
    if not ok:
        return False, feedback

    if len(solutions) < 3:
        return True, ""

    principles = [_principle_key(sol) for sol in solutions]
    if len(set(principles)) == len(solutions) and not _dominant_mechanism_clusters(solutions):
        return True, ""

    try:
        result = _llm_diversity_check(solutions, resources, llm)
        if isinstance(result, dict):
            result = _DiversityCheckResult.model_validate(result)
    except Exception as exc:
        logger.warning("LLM-проверка разнообразия решений не удалась: %s", exc)
        return True, ""

    if result.passed:
        return True, ""

    if result.feedback.strip():
        return False, result.feedback.strip()

    principles = [_principle_key(sol) for sol in solutions]
    clusters = _dominant_mechanism_clusters(solutions)
    issues: list[str] = []
    if result.collapsed_cluster.strip():
        issues.append(f"кластер «{result.collapsed_cluster.strip()}»")
    if not result.distinct_principles:
        issues.append("повторяются ТРИЗ-принципы")
    if not result.distinct_mechanisms:
        issues.append("повторяются механизмы/ресурсы")
    if not result.resolution_axes and result.missing_axes:
        issues.append("не представлены оси разрешения ФП: " + ", ".join(result.missing_axes))
    return False, _format_diversity_feedback(
        issues=issues or ["недостаточное разнообразие набора"],
        clusters=clusters,
        principles=principles,
    )


def select_diverse_solutions(
    solutions: list[dict],
    *,
    limit: int = 5,
) -> list[dict]:
    """
    Отбирает до limit лучших по score решений с максимальным разнообразием.
    Используется после merge попыток, чтобы финальный набор не раздувался.
    """
    if not solutions:
        return []

    ranked = sorted(solutions, key=_solution_score, reverse=True)
    selected: list[dict] = []

    for sol in ranked:
        if len(selected) >= limit:
            break
        candidate = dict(sol)
        if any(_principle_key(candidate) == _principle_key(s) for s in selected):
            continue
        if any(_mechanism_cluster_hits(candidate) & _mechanism_cluster_hits(s) for s in selected):
            continue
        trial = selected + [candidate]
        if len(trial) >= 3:
            ok, _ = _heuristic_diversity_check(trial)
            if not ok:
                continue
        selected.append(candidate)

    seen = {_solution_dedup_key(s) for s in selected}
    for sol in ranked:
        if len(selected) >= limit:
            break
        key = _solution_dedup_key(sol)
        if key in seen:
            continue
        candidate = dict(sol)
        if any(_principle_key(candidate) == _principle_key(s) for s in selected):
            continue
        if any(_mechanism_cluster_hits(candidate) & _mechanism_cluster_hits(s) for s in selected):
            continue
        selected.append(candidate)
        seen.add(key)

    selected = selected[:limit]
    for index, sol in enumerate(selected, start=1):
        sol["id"] = index
    return selected


def _format_constraints(constraints: str | list[str] | None) -> str:
    if not constraints:
        return ""
    if isinstance(constraints, list):
        lines = [str(c).strip() for c in constraints if str(c).strip()]
        return "\n".join(f"• {line}" for line in lines)
    return str(constraints).strip()


def _solution_text(solution: dict) -> str:
    parts = [
        solution.get("title", ""),
        solution.get("mechanism", ""),
        solution.get("applicability", ""),
        solution.get("triz_principle", ""),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def _heuristic_constraint_violation(solution: dict, constraints_text: str) -> tuple[bool, str, str]:
    """Дешёвая эвристика явных и типовых косвенных нарушений constraints без LLM."""
    if not constraints_text.strip():
        return False, "", ""

    constraints_lower = constraints_text.lower()
    text = _solution_text(solution)

    consumables_only = any(m in constraints_lower for m in _CONSUMABLES_ONLY_MARKERS)
    if consumables_only and any(m in text for m in _EQUIPMENT_SOLUTION_MARKERS):
        for marker in _CONSUMABLES_ONLY_MARKERS:
            if marker in constraints_lower:
                violated = constraints_text
                return (
                    True,
                    violated,
                    (
                        "решение предполагает оборудование/автоматизированную систему, "
                        f"что противоречит ограничению «{marker}…»"
                    ),
                )

    material_forbidden = any(m in constraints_lower for m in _MATERIAL_CHANGE_FORBIDDEN_MARKERS)
    if material_forbidden and any(m in text for m in _NEW_PRODUCT_MARKERS):
        for marker in _MATERIAL_CHANGE_FORBIDDEN_MARKERS:
            if marker in constraints_lower:
                return (
                    True,
                    marker,
                    (
                        "решение предполагает разработку нового изделия/катетера, "
                        "что косвенно нарушает запрет на смену материала: "
                        "новое изделие потребует нового материала, конструкции или сертификации"
                    ),
                )

    if "одноразов" in constraints_lower and "нельзя" in constraints_lower:
        if re.search(r"одноразов\w*\s+стакан", constraints_lower):
            if "одноразов" in text and "стакан" in text:
                return (
                    True,
                    "нельзя менять стаканы на одноразовые",
                    "решение предполагает одноразовые стаканы",
                )

    if "отдельный поднос" in constraints_lower and "нельзя" in constraints_lower:
        if re.search(r"поднос\w*\s+на\s+кажд", text) or "отдельный поднос" in text:
            return (
                True,
                "нельзя ставить отдельный поднос на каждый стакан",
                "решение предполагает отдельный поднос на стакан",
            )

    return False, "", ""


def _llm_constraint_check(
    solutions: list[dict],
    constraints: str,
    llm,
) -> _ConstraintCheckResult:
    structured = llm.with_structured_output(_ConstraintCheckResult)
    return structured.invoke(
        [
            SystemMessage(content=_CONSTRAINT_SYSTEM),
            HumanMessage(
                content=_CONSTRAINT_USER.format(
                    constraints=constraints,
                    solutions_json=_format_solutions_for_prompt(solutions),
                )
            ),
        ]
    )


def _check_constraint_violations(
    solutions: list[dict],
    constraints: str | list[str] | None,
    llm,
) -> tuple[list[dict], list[dict], str]:
    """
    Проверяет constraints для каждого решения.

    Returns:
        (valid, rejected, feedback) — feedback непустой, если есть отбракованные.
    """
    constraints_text = _format_constraints(constraints)
    if not constraints_text or not solutions:
        return solutions, [], ""

    heuristic_rejects: dict[int, tuple[str, str]] = {}
    for sol in solutions:
        sid = sol.get("id")
        violates, violated, reason = _heuristic_constraint_violation(sol, constraints_text)
        if violates and sid is not None:
            heuristic_rejects[int(sid)] = (violated, reason)

    llm_rejects: dict[int, tuple[str, str]] = {}
    try:
        result = _llm_constraint_check(solutions, constraints_text, llm)
        if isinstance(result, dict):
            result = _ConstraintCheckResult.model_validate(result)
        for item in result.items:
            if item.violates_constraint:
                llm_rejects[item.solution_id] = (
                    item.violated_constraint or "жёсткое ограничение из брифа",
                    item.reason or "нарушает constraints",
                )
    except Exception as exc:
        logger.warning("LLM-проверка constraints не удалась, только эвристика: %s", exc)

    reject_ids = set(heuristic_rejects) | set(llm_rejects)
    valid: list[dict] = []
    rejected: list[dict] = []
    feedback_lines: list[str] = []

    for sol in solutions:
        sid = sol.get("id")
        if sid is not None and int(sid) in reject_ids:
            rejected.append(sol)
            violated, reason = llm_rejects.get(int(sid)) or heuristic_rejects.get(
                int(sid), ("", "")
            )
            title = sol.get("title", f"id={sid}")
            feedback_lines.append(
                f"#{sid} «{title}» ИСКЛЮЧЕНО (hard fail — нарушение constraints): "
                f"{violated}. {reason}"
            )
        else:
            valid.append(sol)

    feedback = ""
    if feedback_lines:
        feedback = (
            "Решения, нарушающие жёсткие ограничения (отбракованы, нужна замена):\n"
            + "\n".join(feedback_lines)
            + f"\n\nОсталось {len(valid)} решений. Сгенерируй {len(rejected)} замен(у), "
            "строго в пределах constraints (включая косвенные нарушения: "
            "без новых изделий, если запрещена смена материала/конструкции). "
            "Нарушители constraints не включай в ответ."
        )

    return valid, rejected, feedback


def _heuristic_precheck(solutions: list[dict]) -> tuple[bool, str]:
    if not solutions:
        return False, "Список решений пуст — нечего валидировать."

    if len(solutions) < MIN_SOLUTIONS:
        return False, (
            f"Недостаточно решений для отчёта: {len(solutions)} "
            f"(ожидается минимум {MIN_SOLUTIONS})."
        )

    return True, ""


def _llm_checklist(
    solutions: list[dict],
    known_solutions: str,
    why_failed: str,
    resources: str,
    ifr: str,
    llm,
) -> _SolutionChecklistResult:
    structured = llm.with_structured_output(_SolutionChecklistResult)
    return structured.invoke(
        [
            SystemMessage(content=_VALIDATE_SYSTEM),
            HumanMessage(
                content=_VALIDATE_USER.format(
                    ifr=ifr or "—",
                    resources=resources or "—",
                    known_solutions=known_solutions or "—",
                    why_failed=why_failed or "—",
                    solutions_json=_format_solutions_for_prompt(solutions),
                    min_solutions=MIN_SOLUTIONS,
                )
            ),
        ]
    )


def _build_feedback_from_items(
    solutions: list[dict],
    items: list[_SolutionItemCheck],
) -> str:
    by_id = {s.get("id"): s for s in solutions}
    lines: list[str] = []

    for item in items:
        if item.not_dead_end_duplicate and item.uses_specific_resource and item.advances_ifr:
            continue

        sol = by_id.get(item.solution_id, {})
        title = sol.get("title", f"id={item.solution_id}")
        violations: list[str] = []
        if not item.not_dead_end_duplicate:
            violations.append("дублирует тупик из known_solutions/why_failed (семантически)")
        if not item.uses_specific_resource:
            violations.append("не опирается на конкретный ресурс из resources")
        if not item.advances_ifr:
            violations.append("не приближает к ИКР")
        lines.append(f"#{item.solution_id} «{title}»: " + "; ".join(violations))

    if not lines:
        return "Одно или несколько решений не прошли чек-лист."

    return "Решения с нарушениями:\n" + "\n".join(lines)


def _count_quality_passed(
    solutions: list[dict], items: list[_SolutionItemCheck]
) -> tuple[int, list[_SolutionItemCheck]]:
    """Число решений, прошедших все три пункта чек-листа."""
    by_id = {item.solution_id: item for item in items}
    passed_items: list[_SolutionItemCheck] = []
    for sol in solutions:
        sid = sol.get("id")
        if sid is None:
            continue
        item = by_id.get(int(sid))
        if not item:
            continue
        if item.not_dead_end_duplicate and item.uses_specific_resource and item.advances_ifr:
            passed_items.append(item)
    return len(passed_items), passed_items


def validate_solutions(
    solutions: list[dict],
    known_solutions: str,
    why_failed: str,
    resources: str,
    ifr: str,
    llm,
    constraints: str | list[str] | None = None,
) -> tuple[bool, str, list[dict]]:
    """
    Проверяет концепции решений: constraints (hard fail) → чек-лист качества.

    Returns:
        (passed, feedback, valid_solutions) — valid_solutions без нарушителей constraints;
        passed=True если ≥ MIN_SOLUTIONS решений прошли quality+diversity;
        feedback может содержать замечания по отсечённым constraints даже при passed=True.
    """
    constraint_feedback = ""
    if constraints:
        solutions, _rejected, constraint_feedback = _check_constraint_violations(
            solutions, constraints, llm
        )

    ok, precheck_feedback = _heuristic_precheck(solutions)
    if not ok:
        combined = "\n\n".join(part for part in (constraint_feedback, precheck_feedback) if part)
        return False, combined, solutions

    try:
        result = _llm_checklist(solutions, known_solutions, why_failed, resources, ifr, llm)
        if isinstance(result, dict):
            result = _SolutionChecklistResult.model_validate(result)
    except Exception as exc:
        logger.warning("LLM-валидация решений не удалась: %s", exc)
        combined = "\n\n".join(
            part
            for part in (
                constraint_feedback,
                f"Не удалось выполнить LLM-проверку решений: {exc}",
            )
            if part
        )
        return False, combined, solutions

    quality_passed = result.passed
    quality_pass_count, _passed_items = _count_quality_passed(solutions, result.items)
    if quality_pass_count >= MIN_SOLUTIONS:
        quality_passed = True

    quality_feedback = ""
    if not quality_passed:
        if result.feedback.strip():
            quality_feedback = result.feedback.strip()
        else:
            quality_feedback = _build_feedback_from_items(solutions, result.items)

    if len(solutions) < MIN_SOLUTIONS:
        combined = "\n\n".join(
            part
            for part in (
                constraint_feedback,
                quality_feedback,
                f"После отсечения constraints осталось {len(solutions)} решений "
                f"(минимум {MIN_SOLUTIONS}).",
            )
            if part
        )
        return False, combined, solutions

    if not quality_passed:
        combined = "\n\n".join(part for part in (constraint_feedback, quality_feedback) if part)
        return False, combined, solutions

    diversity_ok, diversity_feedback = check_solution_diversity(solutions, resources, llm)
    if not diversity_ok:
        combined = "\n\n".join(part for part in (constraint_feedback, diversity_feedback) if part)
        return False, combined, solutions

    return True, constraint_feedback, solutions
