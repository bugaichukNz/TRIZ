"""Pydantic-модели экспертного TRIZ-отчёта (structured output LLM)."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, computed_field

_SKIPPED_VALUE = "—"
FieldStatus = Literal["confirmed", "skipped", "untouched"]


class InterviewBrief(BaseModel):
    """Структурированный бриф интервью (17 полей FIELD_LABELS)."""

    ne_fact: str = _SKIPPED_VALUE
    ne_where: str = _SKIPPED_VALUE
    ne_when: str = _SKIPPED_VALUE
    consequences: str = _SKIPPED_VALUE
    cause_hypothesis: str = _SKIPPED_VALUE
    system_function: str = _SKIPPED_VALUE
    system_elements: str = _SKIPPED_VALUE
    system_object: str = _SKIPPED_VALUE
    supersystem: str = _SKIPPED_VALUE
    expected_result: str = _SKIPPED_VALUE
    economic_result: str = _SKIPPED_VALUE
    constraints: str = _SKIPPED_VALUE
    resources: str = _SKIPPED_VALUE
    known_solutions: str = _SKIPPED_VALUE
    why_failed: str = _SKIPPED_VALUE
    unrealized_ideas: str = _SKIPPED_VALUE
    experts: str = _SKIPPED_VALUE
    statuses: dict[str, FieldStatus] = Field(default_factory=dict)

    def to_prompt_text(self, messages: list[dict[str, str]] | None = None) -> str:
        """Текст брифа для LLM — тот же формат, что compile_interview_brief."""
        from backend.chat_brief import _append_confirmed_sections, _append_dialog

        confirmed: dict[str, str] = {}
        for field, status in self.statuses.items():
            if status in ("confirmed", "skipped"):
                confirmed[field] = getattr(self, field)

        lines = [
            "# Сводка интервью TRIZ (подтверждена задачедателем)",
            "",
        ]
        _append_confirmed_sections(lines, confirmed)
        if messages:
            _append_dialog(lines, messages)
        return "\n".join(lines).strip()


class SystemContext(BaseModel):
    """Система и окружение."""

    system: str = Field(description="Основная система")
    supersystem: str = Field(description="Надсистема")
    subsystems: list[str] = Field(description="Подсистемы")
    useful_functions: list[str] = Field(description="Полезные функции")
    harmful_effects: list[str] = Field(description="Нежелательные эффекты (НЭ)")
    constraints: list[str] = Field(description="Ограничения")
    resources: list[str] = Field(description="Доступные ресурсы")


class AnalysisBlock(BaseModel):
    """Аналитический блок отчёта."""

    causal_chains: str = Field(description="Причинно-следственные цепочки")
    functional_analysis: str = Field(description="Функциональный анализ")
    resources_analysis: str = Field(description="Выявленные ресурсы")
    contradiction_zones: str = Field(description="Ключевые зоны противоречий")


class TrizToolRow(BaseModel):
    """Применённый инструмент ТРИЗ."""

    tool: str = Field(
        description=(
            "Название инструмента ТРИЗ НА РУССКОМ ЯЗЫКЕ с номером по карте связей, "
            "например: 'Инструмент 11 — Причинно-следственный анализ (ПСА)', "
            "'Инструмент 14 — Компонентно-структурный анализ (КСА)'"
        )
    )
    why_applied: str = Field(description="Почему инструмент применён к данной задаче")
    insight: str = Field(description="Ключевой вывод или инсайт от применения инструмента")
    practical_value: str = Field(description="Практическая ценность результата для решения задачи")


class SolutionConcept(BaseModel):
    """Концепция одного решения с оценками."""

    id: int
    title: str
    triz_principle: str
    mechanism: str
    applicability: str
    risks: str
    effectiveness_score: int = Field(ge=1, le=10)
    complexity_score: int = Field(ge=1, le=10)
    cost_score: int = Field(ge=1, le=10)
    scalability_score: int = Field(ge=1, le=10)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_score(self) -> float:
        """Итоговый балл для ранжирования."""
        return round(
            self.effectiveness_score
            + self.scalability_score
            - (self.complexity_score + self.cost_score) / 2,
            1,
        )


class SolutionSet(BaseModel):
    """Набор концепций решений (второй проход генерации)."""

    solution_concepts: list[SolutionConcept] = Field(min_length=3, max_length=5)


class RecommendationsBlock(BaseModel):
    """Рекомендации к внедрению."""

    priorities: list[str] = Field(description="Приоритеты внедрения")
    priority_solution_id: int
    quick_checks: list[str]
    mvp_pilots: list[str]
    critical_risks: list[str]
    experiments: list[str]
    metrics: list[str]


class FinalConclusionBlock(BaseModel):
    """Итоговый вывод."""

    recommended_solution: str
    key_risk: str
    next_step: str


class ContradictionPair(BaseModel):
    """Техническое и физическое противоречие (перегенерация после валидации ФП)."""

    technical_contradiction: str
    physical_contradiction: str


class ContradictionRepair(BaseModel):
    """ПСА + противоречия (перегенерация после провала валидации ПСА/ФП)."""

    root_cause: str
    causal_chains: str
    technical_contradiction: str
    physical_contradiction: str


class PSARootRepair(BaseModel):
    """Только ПСА (root_cause + causal_chains)."""

    root_cause: str
    causal_chains: str


class TRIZAnalysisCore(BaseModel):
    """Ядро TRIZ-анализа (STEP 1–2): без решений и рекомендаций."""

    problem_description: str = Field(description="Описание задачи в ТРИЗ-терминах")
    assumptions: list[str] = Field(default_factory=list)
    system_context: SystemContext
    technical_contradiction: str
    physical_contradiction: str = Field(
        description=(
            "Одно предложение по формуле: «[элемент]: параметр [P] должен быть [X], "
            "чтобы [A], и должен быть [анти-X], чтобы [B]» — один параметр, X и anti-X"
        )
    )
    contradiction_type: str = Field(
        description=(
            "техническое | физическое | административное | комбинированное; "
            "если physical_contradiction — формула ФП (один параметр, X/anti-X), обязательно «физическое»"
        )
    )
    ideal_final_result: str
    root_cause: str = Field(
        description=(
            "Корневое физическое/химическое явление по итогам ПСА "
            "(не инженерный симптом); основа для ТП и ФП"
        )
    )
    analysis: AnalysisBlock
    triz_tools: list[TrizToolRow] = Field(
        description="Применённые инструменты ТРИЗ с обоснованием (названия только на русском)"
    )
    known_solutions: str = Field(
        default="",
        description="Известные попытки решения из брифа (конкретные тупики, не описание задачи)",
    )
    why_failed: str = Field(
        default="",
        description="Почему известные попытки не сработали",
    )
    unrealized_ideas: str = Field(
        default="",
        description="Нереализованные идеи из брифа",
    )


class TRIZAnalysisResult(BaseModel):
    """Полный экспертный TRIZ-отчёт от LLM."""

    problem_description: str = Field(description="Описание задачи в ТРИЗ-терминах")
    assumptions: list[str] = Field(default_factory=list)
    system_context: SystemContext
    technical_contradiction: str
    physical_contradiction: str
    contradiction_type: str = Field(
        description=(
            "техническое | физическое | административное | комбинированное; "
            "если physical_contradiction — формула ФП (один параметр, X/anti-X), обязательно «физическое»"
        )
    )
    ideal_final_result: str
    root_cause: str = Field(
        description=(
            "Корневое физическое/химическое явление по итогам ПСА "
            "(не инженерный симптом); основа для ТП и ФП"
        )
    )
    analysis: AnalysisBlock
    triz_tools: list[TrizToolRow] = Field(
        description="Применённые инструменты ТРИЗ с обоснованием (названия только на русском)"
    )
    solution_concepts: list[SolutionConcept] = Field(min_length=2)
    recommendations: RecommendationsBlock
    final_conclusion: FinalConclusionBlock
    recommended_principles: list[str] = Field(
        description="Применённые изобретательские принципы (№ и название)"
    )
    executive_summary: str = Field(description="Краткое резюме для руководства (3–5 предложений)")


def solution_total_score(solution: SolutionConcept | dict) -> float:
    """Итоговый балл решения (для dict или модели)."""
    if isinstance(solution, dict):
        return round(
            solution["effectiveness_score"]
            + solution["scalability_score"]
            - (solution["complexity_score"] + solution["cost_score"]) / 2,
            1,
        )
    return solution.total_score


def build_recommendations(core: dict, solutions: list[dict]) -> dict:
    """Рекомендации, итоговый вывод, принципы и executive_summary (без LLM)."""
    problem = core.get("problem_description", "")
    tp = core.get("technical_contradiction", "")

    if not solutions:
        return {
            "recommendations": RecommendationsBlock(
                priorities=[],
                priority_solution_id=1,
                quick_checks=[],
                mvp_pilots=[],
                critical_risks=["Решения не сгенерированы"],
                experiments=["Повторить этап генерации решений"],
                metrics=[],
            ).model_dump(),
            "final_conclusion": FinalConclusionBlock(
                recommended_solution="—",
                key_risk="Концепции решений отсутствуют",
                next_step="Повторить генерацию решений или уточнить исходные данные",
            ).model_dump(),
            "recommended_principles": [],
            "executive_summary": (
                f"{problem[:400]} Противоречие: {tp[:200]}."
                if problem or tp
                else "Анализ выполнен; решения не сформированы."
            ),
        }

    ranked = sorted(solutions, key=solution_total_score, reverse=True)
    best = ranked[0]
    best_id = best["id"]

    principles: list[str] = []
    seen: set[str] = set()
    for sol in solutions:
        principle = (sol.get("triz_principle") or "").strip()
        if principle and principle not in seen:
            seen.add(principle)
            principles.append(principle)

    critical_risks = [
        f"#{sol['id']} {sol['title']}: {sol.get('risks', '')[:200]}"
        for sol in ranked[:3]
        if sol.get("risks")
    ]

    recommendations = RecommendationsBlock(
        priorities=[f"#{sol['id']}: {sol['title']}" for sol in ranked],
        priority_solution_id=best_id,
        quick_checks=[
            f"Проверить гипотезу «{sol['title']}»: {sol.get('mechanism', '')[:150]}"
            for sol in ranked[:2]
        ],
        mvp_pilots=[
            f"Пилот #{sol['id']}: {sol.get('applicability', '')[:150]}" for sol in ranked[:2]
        ],
        critical_risks=critical_risks or ["Уточнить риски внедрения у ответственных экспертов"],
        experiments=[
            f"Эксперимент для #{sol['id']}: оценить {sol.get('title', 'решение')}"
            for sol in ranked[:3]
        ],
        metrics=[
            "Достигнутые показатели vs целевые из постановки задачи",
            f"Эффективность приоритетного решения #{best_id} (балл {solution_total_score(best)})",
            "Срок и стоимость пилотного внедрения",
        ],
    )

    final_conclusion = FinalConclusionBlock(
        recommended_solution=(
            f"#{best_id} «{best['title']}» (итоговый балл {solution_total_score(best)}): "
            f"{best.get('mechanism', '')[:300]}"
        ),
        key_risk=(best.get("risks") or ranked[0].get("risks") or "—")[:400],
        next_step=(
            f"Запустить быструю проверку решения #{best_id}: {best.get('applicability', '')[:200]}"
        ),
    )

    executive_summary = (
        f"{problem[:350]} "
        f"Тип противоречия: {core.get('contradiction_type', '—')}. "
        f"Приоритетное решение — #{best_id} «{best['title']}» "
        f"(балл {solution_total_score(best)}). "
        f"Ключевой риск: {(best.get('risks') or '—')[:150]}."
    ).strip()

    return {
        "recommendations": recommendations.model_dump(),
        "final_conclusion": final_conclusion.model_dump(),
        "recommended_principles": principles,
        "executive_summary": executive_summary,
    }


class PhysicalEffect(BaseModel):
    """Физический, химический или геометрический эффект из указателя ТРИЗ."""

    id: str = Field(description="Slug латиницей, напр. magnetostriction")
    name: str = Field(description="Название на русском, напр. «Магнитострикция»")
    category: Literal["физический", "химический", "геометрический"]
    description: str = Field(description="2–4 предложения: суть эффекта")
    input_action: str = Field(description="Что подаём на вход, напр. «магнитное поле»")
    output_action: str = Field(description="Что получаем, напр. «изменение линейных размеров»")
    functions: list[str] = Field(description="Обобщённые функции из контролируемого словаря EFFECT_FUNCTIONS")
    limitations: str = Field(description="Границы применимости, типичные величины")
    examples: list[str] = Field(description="1–3 примера применения в технике", min_length=1, max_length=3)
    task_phrases: list[str] = Field(
        default_factory=list,
        description="Типовые инженерные задачи, решаемые эффектом (глагол + объект + условие)",
    )
    provenance: Literal["planned", "extra"] = Field(
        default="planned",
        description="planned — из suggested_ids батча; extra — сверх плана LLM",
    )


class EffectsCorpus(BaseModel):
    """Контейнер корпуса физических эффектов для семантического поиска."""

    effects: list[PhysicalEffect]
    version: str = Field(description="Версия корпуса, напр. 1.0.0")


class EffectsBatch(BaseModel):
    """Пакет эффектов для батчевой генерации LLM (до 20 записей)."""

    effects: list[PhysicalEffect] = Field(min_length=1, max_length=20)


class EffectTaskPhrasesRow(BaseModel):
    """Инженерные постановки задач для одного физэффекта."""

    id: str
    task_phrases: list[str] = Field(min_length=4, max_length=6)


class EffectsTaskEnrichmentBatch(BaseModel):
    """Батч обогащения task_phrases (до 20 эффектов)."""

    effects: list[EffectTaskPhrasesRow] = Field(min_length=1, max_length=20)


class EffectQueries(BaseModel):
    """Поисковые запросы для RAG по корпусу физэффектов."""

    queries: list[str] = Field(max_length=3)


PipelineStepStatus = Literal["ok", "ok_with_retries", "warning"]


class AnalysisProfile(BaseModel):
    """Per-run профиль TRIZ-анализа: инструменты и параметры пайплайна."""

    tools_enabled: dict[str, bool] = Field(
        description=(
            "Ключи: tool_2_problem_statement, tool_14_ksa, tool_11_psa, "
            "supfield_analysis, contradiction_matrix, trimming"
        ),
    )
    effects_rag: bool = True
    target_solutions: int = Field(default=4, ge=2, le=8)
    psa_fp_validation: bool = True

    @classmethod
    def default_profile(cls) -> "AnalysisProfile":
        from backend.config import settings
        from backend.llm.tools_registry import DEFAULT_TOOLS_ENABLED

        return cls(
            tools_enabled=dict(DEFAULT_TOOLS_ENABLED),
            effects_rag=settings.effects_rag_enabled,
            target_solutions=4,
            psa_fp_validation=True,
        )

    @classmethod
    def resolve(cls, profile: "AnalysisProfile | None") -> "AnalysisProfile":
        return profile if profile is not None else cls.default_profile()

    def is_default(self) -> bool:
        default = self.default_profile()
        return (
            self.tools_enabled == default.tools_enabled
            and self.effects_rag == default.effects_rag
            and self.target_solutions == default.target_solutions
            and self.psa_fp_validation == default.psa_fp_validation
        )

    def core_prompt_suffix(self) -> str:
        """Дополнение к user-промпту core-анализа; пустая строка для дефолтного профиля."""
        if self.is_default():
            return ""

        from backend.llm.tools_registry import TOOLS_REGISTRY

        enabled_titles: list[str] = []
        excluded_titles: list[str] = []
        for key, enabled in self.tools_enabled.items():
            entry = TOOLS_REGISTRY.get(key)
            if entry is None:
                continue
            title = entry["title"]
            if enabled:
                enabled_titles.append(title)
            else:
                excluded_titles.append(title)

        lines: list[str] = []
        if enabled_titles:
            lines.append(
                "Обязательные инструменты для этого анализа: "
                + ", ".join(enabled_titles)
                + "."
            )
        if excluded_titles:
            lines.append("Исключи инструменты: " + ", ".join(excluded_titles) + ".")
        return "\n\n" + "\n".join(lines) if lines else ""

    def solution_count_label(self) -> str:
        """«3–5» при дефолтном target_solutions=4, иначе точное число."""
        if self.target_solutions == 4:
            return "3–5"
        return str(self.target_solutions)

    def describe_deviations(self) -> list[str]:
        """Человекочитаемый список отличий от дефолтного профиля."""
        if self.is_default():
            return []

        from backend.llm.tools_registry import TOOLS_REGISTRY

        default = self.default_profile()
        notes: list[str] = []

        for key, enabled in self.tools_enabled.items():
            if enabled == default.tools_enabled.get(key):
                continue
            entry = TOOLS_REGISTRY.get(key)
            title = entry["title"] if entry else key
            notes.append(f"{'включён' if enabled else 'отключён'}: {title}")

        if self.effects_rag != default.effects_rag:
            notes.append(
                f"effects-RAG: {'включён' if self.effects_rag else 'отключён'}"
            )
        if self.target_solutions != default.target_solutions:
            notes.append(f"число решений: {self.target_solutions}")
        if self.psa_fp_validation != default.psa_fp_validation:
            notes.append(
                f"валидация ПСА/ФП: {'включена' if self.psa_fp_validation else 'отключена'}"
            )
        return notes


class PipelineStepTrace(BaseModel):
    """Трассировка одного этапа пайплайна TRIZChain.solve."""

    step_id: str
    title: str
    status: PipelineStepStatus
    attempts: int
    tools_used: list[str]
    validator_notes: list[str]
    duration_ms: int


class StageArtifact(BaseModel):
    """Снимок промежуточного состояния пайплайна TRIZChain.solve."""

    step_id: str
    payload: dict
    created_at: str
    profile_hash: str


def compute_profile_hash(profile: AnalysisProfile) -> str:
    """SHA-256 хеш канонически сериализованного AnalysisProfile."""
    canonical = json.dumps(profile.model_dump(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def enrich_legacy_fields(payload: dict) -> dict:
    """Добавляет поля обратной совместимости для старого UI/API."""
    payload["contradiction"] = payload.get("technical_contradiction", "")
    concepts = payload.get("solution_concepts") or []
    payload["solutions"] = [
        f"{c['title']}: {c['mechanism']}" if isinstance(c, dict) else f"{c.title}: {c.mechanism}"
        for c in concepts
    ]
    analysis = payload.get("analysis") or {}
    tools = payload.get("triz_tools") or []
    tools_text = "; ".join(t["tool"] if isinstance(t, dict) else t.tool for t in tools[:5])
    payload["reasoning"] = (
        f"{payload.get('executive_summary', '')}\n\n"
        f"Инструменты: {tools_text}.\n"
        f"Причинные связи: {analysis.get('causal_chains', '')[:500]}"
    ).strip()
    return payload
