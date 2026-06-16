"""Валидация формулировки физического противоречия (ФП)."""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_BILATERAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"долж(?:ен|на|но)\s+быть\s+.+?\s+и\s+долж(?:ен|на|но)\s+быть", re.IGNORECASE | re.DOTALL),
    re.compile(r"должен\s+.{3,120}?\s+и\s+должен", re.IGNORECASE | re.DOTALL),
    re.compile(r"должен\s+быть\s+.+?\s+и\s+(?:при\s+этом\s+)?(?:быть\s+)?", re.IGNORECASE | re.DOTALL),
    re.compile(r"с\s+одной\s+стороны.+с\s+другой", re.IGNORECASE | re.DOTALL),
    re.compile(r"одновременно\s+.{3,80}?\s+и\s+", re.IGNORECASE),
    re.compile(r"\bи\s+при\s+этом\b", re.IGNORECASE),
    re.compile(r"\bно\s+также\s+должен\b", re.IGNORECASE),
]

_SPATIAL_SPLIT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bвнутри\b.+\bснаружи\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bснаружи\b.+\bвнутри\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bсверху\b.+\bснизу\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bснизу\b.+\bсверху\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bна\s+поднос\w*\b.+\bснаруж\w*\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bснаруж\w*\b.+\bна\s+поднос\w*\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bвнешн\w*\s+поверхност\w*\b.+\bвнутренн\w*\s+поверхност\w*\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bвнутренн\w*\s+поверхност\w*\b.+\bвнешн\w*\s+поверхност\w*\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bс\s+одной\s+стороны\b.+\bс\s+другой\s+стороны\b", re.IGNORECASE | re.DOTALL),
]

_TASK_PHASE_HINT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"инкубац", re.IGNORECASE),
    re.compile(r"эксперимент", re.IGNORECASE),
    re.compile(r"\bсначала\b.+\bпотом\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bпотом\b.+\bсначала\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"на этапе", re.IGNORECASE),
    re.compile(r"разн\w*\s+этап", re.IGNORECASE),
    re.compile(r"разн\w*\s+фаз", re.IGNORECASE),
    re.compile(r"подготовк\w*.+работ", re.IGNORECASE | re.DOTALL),
    re.compile(r"загрузк\w*.+обработ", re.IGNORECASE | re.DOTALL),
    re.compile(r"при перенос", re.IGNORECASE),
    re.compile(r"перед эксперимент", re.IGNORECASE),
    re.compile(r"широк\w*\s+камер\w*.+узк\w*\s+канал", re.IGNORECASE | re.DOTALL),
    re.compile(r"инкубац\w*.+эксперимент", re.IGNORECASE | re.DOTALL),
]

_TEMPORAL_FP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"на фазе\s+.+?\s+долж", re.IGNORECASE | re.DOTALL),
    re.compile(r"на этапе\s+.+?\s+долж", re.IGNORECASE | re.DOTALL),
    re.compile(r"при инкубац\w*.+?\s+и\s+(?:на фазе|при|в|на этапе)", re.IGNORECASE | re.DOTALL),
    re.compile(r"долж\w+\s+быть\s+.+?\s+при инкубац", re.IGNORECASE | re.DOTALL),
    re.compile(
        r"при инкубац\w*.+?долж\w+.+?\s+и\s+.+?(?:при|в|на)\s+эксперимент",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"на фазе\s+.+?\s+долж\w+.+?\s+и\s+на фазе\s+.+?\s+долж",
        re.IGNORECASE | re.DOTALL,
    ),
]

_ANTONYM_PAIRS: list[tuple[str, str]] = [
    ("широк", "узк"),
    ("больш", "мал"),
    ("длинн", "коротк"),
    ("высок", "низк"),
    ("толст", "тонк"),
    ("твёрд", "мягк"),
    ("тверд", "мягк"),
    ("горяч", "холод"),
    ("лёгк", "тяжел"),
    ("легк", "тяжел"),
    ("быстр", "медлен"),
    ("прочн", "хрупк"),
    ("гладк", "шершав"),
    ("плотн", "рыхл"),
    ("прозрачн", "непрозрачн"),
    ("открыт", "закрыт"),
    ("подвижн", "неподвижн"),
    ("жёстк", "гибк"),
    ("жестк", "гибк"),
    ("порист", "сплошн"),
    ("нагрет", "охлажд"),
    ("мокр", "сух"),
    ("сух", "мокр"),
]

_FP_FORMULA_PATTERN = re.compile(
    r"^(.+?):\s*параметр\s+(.+?)\s+долж(?:ен|на|но)\s+быть\s+(.+?),\s*чтобы\s+(.+?),\s*и\s+долж(?:ен|на|но)\s+быть\s+(.+?),\s*чтобы\s+(.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

_FP_FORMULA_TEMPORAL_PATTERN = re.compile(
    r"^(.+?):\s*параметр\s+(.+?)\s+"
    r"(?:на фазе|на этапе|при)\s+(.+?)\s+"
    r"долж(?:ен|на|но)\s+быть\s+(.+?),\s*чтобы\s+(.+?),\s*"
    r"и\s+(?:на фазе|на этапе|при)\s+(.+?)\s+"
    r"долж(?:ен|на|но)\s+быть\s+(.+?),\s*чтобы\s+(.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)

_VALIDATE_SYSTEM = """Ты — методический эксперт ТРИЗ. Проверяешь формулировку физического противоречия (ФП) по строгому чек-листу.
Не оценивай «в целом хорошо ли» — отвечай только по пунктам ниже.
Все формулировки feedback — на русском языке."""

_VALIDATE_USER = """Техническое противоречие (ТП) для контекста:
{technical_contradiction}

Физическое противоречие (ФП) для проверки:
{physical_contradiction}

Чек-лист (все четыре пункта обязательны для passed=true):

1. single_parameter — назван ровно ОДИН параметр одного элемента.
   Противоположные значения одного параметра (низкая/высокая температура, мокрый/сухой) — это ОДИН параметр, не два.
   НЕ single_parameter: разные места/части («внутри/снаружи», «на подносе/снаружи»), разные объекты, «система в целом» без конкретики.

2. dual_requirement — явно заявлено, что этот параметр/элемент должен быть и X, и anti-X (противоположное состояние/свойство).

3. useful_functions_justified — каждое из двух требований (X и anti-X) обосновано своей отдельной полезной функцией: зачем нужен X и зачем нужен anti-X.

4. both_values_inherently_desirable — ОБА значения параметра (X и anti-X) сами по себе желательны для системы.
   Настоящее ФП — конфликт двух польз, а не «польза против абсурда».
   НЕ both_values_inherently_desirable: одна половина — заведомо нежелательное состояние (высокие потери, низкая прочность, большой брак, сильный износ), которое выдают за пользу через «чтобы…»
   (например, «оптические потери должны быть высокими, чтобы избежать линзовой системы» — высокие потери сами по себе никому не нужны).

Верни passed=true только если ВСЕ четыре пункта выполнены.
В feedback перечисли конкретно, какие пункты не выполнены и что именно исправить в формулировке ФП."""


class _FPChecklistResult(BaseModel):
    passed: bool
    feedback: str = Field(description="Что не так; пустая строка если passed=true")
    single_parameter: bool
    dual_requirement: bool
    useful_functions_justified: bool
    both_values_inherently_desirable: bool


class _FPValueDesirabilityResult(BaseModel):
    inherently_desirable: bool = Field(
        description=(
            "true, если значение параметра само по себе желательно для системы; "
            "false, если это заведомо нежелательное/абсурдное состояние, "
            "которое маскируют под пользу"
        )
    )
    feedback: str = Field(
        description="Кратко почему значение нежелательно само по себе; пустая строка если inherently_desirable=true"
    )


class _FPRelevanceResult(BaseModel):
    related: bool = Field(
        description="true, если параметр P связан с корневой причиной НЭ (root_cause)"
    )
    feedback: str = Field(
        description="Кратко почему параметр не связан с root_cause; пустая строка если related=true"
    )


_RELEVANCE_SYSTEM = """Ты — методический эксперт ТРИЗ. Отвечаешь одним лёгким вопросом о релевантности параметра ФП.
Не оценивай грамматику и шаблон формулировки — только связь параметра с корневой причиной НЭ.
Будь строгим: «тот же объект в задаче» ≠ «параметр связан с root_cause»."""

_RELEVANCE_USER = """Корневая причина нежелательного эффекта (root_cause):
{root_cause}

Физическое противоречие (ФП):
{physical_contradiction}

Параметр P из формулировки ФП: {parameter}

Вопрос: связан ли параметр «{parameter}» с корневой причиной НЭ (root_cause)?

Верни related=true только если P — это та же физическая величина (или её непосредственный драйвер), которая фигурирует в механизме root_cause. Изменение P должно напрямую усиливать или ослаблять явление из root_cause.

Верни related=false, если:
- параметр подогнан под шаблон ФП, но описывает постороннее свойство (цвет, вкус, эстетика, удобство питья и т.п.);
- параметр относится к тому же элементу системы, но к другому физическому процессу, не указанному в root_cause (например, вязкость напитка при root_cause о каплях воды на подносе)."""

_DESIRABILITY_SYSTEM = """Ты — методический эксперт ТРИЗ. Оцениваешь ОДНО требование из формулировки ФП.
Не смотри на вторую половину противоречия и не оценивай всё ФП целиком — только указанное значение параметра.
Отделяй «значение само по себе желательно для системы» от «ради побочного эффекта в формулировке «чтобы…» притягивают заведомо плохое состояние».
Все формулировки feedback — на русском языке."""

_DESIRABILITY_USER = """Техническое противоречие (ТП) для контекста:
{technical_contradiction}

Физическое противоречие (ФП):
{physical_contradiction}

Элемент: {element}
Параметр: {parameter}
Значение параметра для проверки: {value}
Заявленная полезная функция (чтобы…): {purpose}

Вопрос: является ли значение «{value}» для параметра «{parameter}» элемента «{element}» САМО ПО СЕБЕ желательным для системы в этой задаче?

Верни inherently_desirable=true, если такое значение параметра — нормальная, осмысленная цель (даже если конфликтует с другим требованием в ФП).

Верни inherently_desirable=false, если:
- это заведомо нежелательное/вредное состояние (высокие потери, низкая прочность, большой брак, высокий износ, сильные потери энергии/сигнала…), которое маскируют под пользу;
- «чтобы» оправдывает абсурд (например, «высокие оптические потери, чтобы избежать линзовой системы» — высокие потери сами по себе никому не нужны);
- полезная функция — лишь оправдание побочного ущерба, а не реальная польза от этого значения."""


def _collect_task_text_for_phases(core: dict, problem: str = "") -> str:
    """Собирает текст задачи для поиска признаков фазности процесса."""
    parts: list[str] = []
    if problem.strip():
        parts.append(problem.strip())
    for key in ("problem_description",):
        val = core.get(key)
        if val:
            parts.append(str(val))

    for key in ("unrealized_ideas", "known_solutions", "why_failed"):
        val = core.get(key)
        if isinstance(val, list):
            parts.extend(str(v) for v in val if str(v).strip())
        elif val:
            parts.append(str(val))

    analysis = core.get("analysis") or {}
    for key in ("harmful_effects",):
        val = analysis.get(key)
        if isinstance(val, list):
            parts.extend(str(v) for v in val if str(v).strip())

    ctx = core.get("system_context") or {}
    for key in ("useful_functions", "harmful_effects", "constraints"):
        val = ctx.get(key)
        if isinstance(val, list):
            parts.extend(str(v) for v in val if str(v).strip())
        elif val:
            parts.append(str(val))

    return "\n".join(parts)


def task_has_process_phases(core: dict, problem: str = "") -> bool:
    """True, если в условии задачи есть признаки разных фаз процесса."""
    text = _collect_task_text_for_phases(core, problem)
    if not text.strip():
        return False
    lowered = text.lower()
    return any(p.search(lowered) for p in _TASK_PHASE_HINT_PATTERNS)


def fp_has_temporal_resolution(fp_text: str) -> bool:
    """True, если ФП явно разделяет требования по фазам/времени."""
    text = (fp_text or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return any(p.search(lowered) for p in _TEMPORAL_FP_PATTERNS)


def validate_fp_resolution_axis(fp_text: str, core: dict, problem: str = "") -> tuple[bool, str]:
    """
    Отклоняет статическое ФП, если в задаче явна фазность процесса.
    """
    if not task_has_process_phases(core, problem):
        return True, ""

    if fp_has_temporal_resolution(fp_text):
        return True, ""

    return (
        False,
        "В задаче есть разные фазы процесса (инкубация/эксперимент, сначала/потом и т.п.), "
        "но ФП сформулировано статически (X и anti-X без указания фаз). "
        "Перебери оси разрешения: приоритет — ВРЕМЯ. "
        "Сформулируй по формуле B: «параметр [P] на фазе [A] должен быть [X]… "
        "и на фазе [B] должен быть [anti-X]…» с явными названиями фаз из брифа.",
    )


def _parse_fp_formula(fp_text: str) -> tuple[str, str, str, str, str, str] | None:
    """Разбирает ФП по шаблону; None если шаблон не соблюдён."""
    text = (fp_text or "").strip()
    if not text:
        return None

    match = _FP_FORMULA_TEMPORAL_PATTERN.match(text)
    if match:
        element, parameter, _phase_a, x_value, x_purpose, _phase_b, anti_x_value, anti_x_purpose = (
            g.strip() for g in match.groups()
        )
        if all((element, parameter, x_value, x_purpose, anti_x_value, anti_x_purpose)):
            return element, parameter, x_value, x_purpose, anti_x_value, anti_x_purpose

    match = _FP_FORMULA_PATTERN.match(text)
    if not match:
        return None

    groups = tuple(g.strip() for g in match.groups())
    if not all(groups):
        return None

    lowered = text.lower()
    has_antonyms = any(
        stem_a in lowered and stem_b in lowered for stem_a, stem_b in _ANTONYM_PAIRS
    )
    has_dual_clause = "должн" in lowered and " и должн" in lowered
    if not has_antonyms and not has_dual_clause:
        return None

    return groups  # type: ignore[return-value]


def _matches_fp_formula(fp_text: str) -> bool:
    """Детерминированная проверка шаблона «[элемент]: параметр [P] должен быть [X], чтобы [A], и должен быть [anti-X], чтобы [B]»."""
    return _parse_fp_formula(fp_text) is not None


def looks_like_fp_formulation(fp_text: str) -> bool:
    """True, если текст — формула ФП (один параметр одного элемента, X и anti-X)."""
    return _matches_fp_formula(fp_text)


_CONTRADICTION_TYPE_PHYSICAL = "физическое"


def check_contradiction_type_consistency(core: dict) -> tuple[bool, str]:
    """
    Проверяет согласованность contradiction_type с physical_contradiction.

    Returns:
        (consistent, feedback) — feedback пустой при consistent=True.
    """
    fp = (core.get("physical_contradiction") or "").strip()
    if not looks_like_fp_formulation(fp):
        return True, ""

    current = (core.get("contradiction_type") or "").strip().lower()
    if current == _CONTRADICTION_TYPE_PHYSICAL:
        return True, ""

    previous = (core.get("contradiction_type") or "").strip() or "—"
    return (
        False,
        f"contradiction_type «{previous}» не согласован с physical_contradiction: "
        "текст сформулирован как ФП (один параметр, X и anti-X), "
        "поэтому тип должен быть «физическое».",
    )


def reconcile_contradiction_type(core: dict) -> tuple[dict, str]:
    """
    Приводит contradiction_type в соответствие с physical_contradiction.

    Returns:
        (core, note) — note непустая, если тип был исправлен.
    """
    consistent, _feedback = check_contradiction_type_consistency(core)
    if consistent:
        return core, ""

    previous = (core.get("contradiction_type") or "").strip() or "—"
    core["contradiction_type"] = _CONTRADICTION_TYPE_PHYSICAL
    note = (
        f"contradiction_type исправлен: «{previous}» → «физическое» "
        "(physical_contradiction содержит формулу ФП)."
    )
    logger.info("reconcile_contradiction_type: %s", note)
    return core, note


def _has_spatial_split(fp_text: str) -> tuple[bool, str]:
    """Отклоняет маскировку ФП через разнесение по местам/частям объекта."""
    text = (fp_text or "").strip()
    if not text:
        return False, ""

    lowered = text.lower()
    for pattern in _SPATIAL_SPLIT_PATTERNS:
        if pattern.search(lowered):
            return True, (
                "ФП сформулировано через разные места или части объекта "
                "(внутри/снаружи, на подносе/снаружи и т.п.) — это не один параметр "
                "в противоречии, а пространственное разделение. Укажи один параметр "
                "одного элемента с двумя взаимоисключающими значениями."
            )

    return False, ""


def _has_bilateralism(fp_text: str) -> tuple[bool, str]:
    """Дешёвая эвристика двусторонности ФП без LLM."""
    text = (fp_text or "").strip()
    if not text:
        return False, "ФП пустое — нет формулировки противоречия."

    lowered = text.lower()

    for pattern in _BILATERAL_PATTERNS:
        if pattern.search(lowered):
            return True, ""

    for stem_a, stem_b in _ANTONYM_PAIRS:
        if stem_a in lowered and stem_b in lowered:
            return True, ""

    return False, (
        "В формулировке ФП не обнаружена двусторонность: нет противопоставления "
        "«должен быть X и должен быть anti-X» или антонимичной пары свойств "
        "(например, широкий/узкий, твёрдый/мягкий)."
    )


def _llm_value_desirability(
    element: str,
    parameter: str,
    value: str,
    purpose: str,
    physical_contradiction: str,
    technical_contradiction: str,
    llm,
) -> _FPValueDesirabilityResult:
    structured = llm.with_structured_output(_FPValueDesirabilityResult)
    return structured.invoke(
        [
            SystemMessage(content=_DESIRABILITY_SYSTEM),
            HumanMessage(
                content=_DESIRABILITY_USER.format(
                    technical_contradiction=technical_contradiction or "—",
                    physical_contradiction=physical_contradiction,
                    element=element,
                    parameter=parameter,
                    value=value,
                    purpose=purpose,
                )
            ),
        ]
    )


def _llm_fp_values_desirability(
    parsed: tuple[str, str, str, str, str, str],
    physical_contradiction: str,
    technical_contradiction: str,
    llm,
) -> tuple[bool, str]:
    """Проверяет, что обе половины ФП — само по себе желательные значения параметра."""
    element, parameter, x_value, x_purpose, anti_x_value, anti_x_purpose = parsed
    halves = (
        (x_value, x_purpose),
        (anti_x_value, anti_x_purpose),
    )
    failed: list[str] = []

    for value, purpose in halves:
        try:
            result = _llm_value_desirability(
                element,
                parameter,
                value,
                purpose,
                physical_contradiction,
                technical_contradiction,
                llm,
            )
            if isinstance(result, dict):
                result = _FPValueDesirabilityResult.model_validate(result)
        except Exception as exc:
            logger.warning(
                "LLM-проверка желательности значения ФП (%s=%s) не удалась: %s",
                parameter,
                value,
                exc,
            )
            return False, (
                f"Не удалось проверить, желательно ли значение «{value}» "
                f"параметра «{parameter}»: {exc}"
            )

        if result.inherently_desirable:
            continue

        if result.feedback.strip():
            failed.append(
                f"«{value}» — {result.feedback.strip()}"
            )
        else:
            failed.append(
                f"«{value}» параметра «{parameter}» само по себе нежелательно для системы"
            )

    if not failed:
        return True, ""

    return (
        False,
        "ФП маскирует нежелательное состояние под пользу: "
        + "; ".join(failed)
        + ". Настоящее ФП — конфликт двух польз (оба значения параметра по-своему полезны), "
        "а не «польза против абсурда». Переформулируй обе половины.",
    )


def _llm_parameter_relevance(
    parameter: str,
    physical_contradiction: str,
    root_cause: str,
    llm,
) -> _FPRelevanceResult:
    structured = llm.with_structured_output(_FPRelevanceResult)
    return structured.invoke(
        [
            SystemMessage(content=_RELEVANCE_SYSTEM),
            HumanMessage(
                content=_RELEVANCE_USER.format(
                    root_cause=root_cause or "—",
                    physical_contradiction=physical_contradiction,
                    parameter=parameter,
                )
            ),
        ]
    )


def _llm_checklist(
    physical_contradiction: str,
    technical_contradiction: str,
    llm,
) -> _FPChecklistResult:
    structured = llm.with_structured_output(_FPChecklistResult)
    return structured.invoke(
        [
            SystemMessage(content=_VALIDATE_SYSTEM),
            HumanMessage(
                content=_VALIDATE_USER.format(
                    technical_contradiction=technical_contradiction or "—",
                    physical_contradiction=physical_contradiction,
                )
            ),
        ]
    )


def validate_fp(
    physical_contradiction: str,
    technical_contradiction: str,
    llm,
    *,
    root_cause: str = "",
    core: dict | None = None,
    problem: str = "",
) -> tuple[bool, str]:
    """
    Проверяет формулировку ФП: эвристики формы, затем LLM.

    При совпадении с детерминированным шаблоном форма считается валидной;
    дополнительно LLM проверяет желательность каждой половины ФП и (при наличии)
    релевантность параметра root_cause. Пропуск только если все проверки зелёные.
    Иначе — полный LLM-чек-лист.

    Returns:
        (passed, feedback) — feedback пустой при passed=True, иначе описание проблем.
    """
    if core is not None:
        from backend.llm.psa_validator import validate_fp_not_rejected_component

        ok_rej, fb_rej = validate_fp_not_rejected_component(physical_contradiction, core)
        if not ok_rej:
            return False, fb_rej

        axis_ok, axis_fb = validate_fp_resolution_axis(physical_contradiction, core, problem)
        if not axis_ok:
            return False, axis_fb

    spatial, spatial_feedback = _has_spatial_split(physical_contradiction)
    if spatial:
        return False, spatial_feedback

    ok, heuristic_feedback = _has_bilateralism(physical_contradiction)
    if not ok:
        return False, heuristic_feedback

    parsed = _parse_fp_formula(physical_contradiction)
    if parsed is not None:
        _element, parameter, *_rest = parsed

        desirability_ok, desirability_feedback = _llm_fp_values_desirability(
            parsed, physical_contradiction, technical_contradiction, llm
        )
        if not desirability_ok:
            return False, desirability_feedback

        if (root_cause or "").strip():
            try:
                relevance = _llm_parameter_relevance(
                    parameter, physical_contradiction, root_cause, llm
                )
                if isinstance(relevance, dict):
                    relevance = _FPRelevanceResult.model_validate(relevance)
            except Exception as exc:
                logger.warning("LLM-проверка релевантности параметра ФП не удалась: %s", exc)
                return False, f"Не удалось проверить релевантность параметра ФП: {exc}"

            if relevance.related:
                return True, ""

            if relevance.feedback.strip():
                return False, relevance.feedback.strip()

            return (
                False,
                f"Параметр «{parameter}» не связан с корневой причиной НЭ: {root_cause}. "
                "Выберите параметр, который непосредственно участвует в механизме нежелательного эффекта.",
            )

        return True, ""

    try:
        result = _llm_checklist(physical_contradiction, technical_contradiction, llm)
        if isinstance(result, dict):
            result = _FPChecklistResult.model_validate(result)
    except Exception as exc:
        logger.warning("LLM-валидация ФП не удалась: %s", exc)
        return False, f"Не удалось выполнить LLM-проверку ФП: {exc}"

    if result.passed:
        return True, ""

    if result.feedback.strip():
        return False, result.feedback.strip()

    failed: list[str] = []
    if not result.single_parameter:
        failed.append(
            "не назван ровно один параметр/элемент системы"
        )
    if not result.dual_requirement:
        failed.append(
            "не заявлено, что элемент должен быть и X, и anti-X"
        )
    if not result.useful_functions_justified:
        failed.append(
            "не обоснованы отдельные полезные функции для X и anti-X"
        )
    if not result.both_values_inherently_desirable:
        failed.append(
            "одна из половин ФП — заведомо нежелательное значение параметра, "
            "а не самостоятельная польза (конфликт «польза против абсурда»)"
        )
    return False, "ФП не прошло чек-лист: " + "; ".join(failed) + "."
