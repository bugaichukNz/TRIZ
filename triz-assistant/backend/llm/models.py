"""Pydantic-модели экспертного TRIZ-отчёта (structured output LLM)."""

from pydantic import BaseModel, Field, computed_field


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
    executive_summary: str = Field(
        description="Краткое резюме для руководства (3–5 предложений)"
    )


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
            f"Пилот #{sol['id']}: {sol.get('applicability', '')[:150]}"
            for sol in ranked[:2]
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
            f"Запустить быструю проверку решения #{best_id}: "
            f"{best.get('applicability', '')[:200]}"
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
    tools_text = "; ".join(
        t["tool"] if isinstance(t, dict) else t.tool for t in tools[:5]
    )
    payload["reasoning"] = (
        f"{payload.get('executive_summary', '')}\n\n"
        f"Инструменты: {tools_text}.\n"
        f"Причинные связи: {analysis.get('causal_chains', '')[:500]}"
    ).strip()
    return payload
