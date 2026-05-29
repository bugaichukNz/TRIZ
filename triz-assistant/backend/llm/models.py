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

    tool: str
    why_applied: str
    insight: str
    practical_value: str


class SolutionConcept(BaseModel):
    """Концепция решения с оценками."""

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


class TRIZAnalysisResult(BaseModel):
    """Полный экспертный TRIZ-отчёт от LLM."""

    problem_description: str = Field(description="Описание задачи в ТРИЗ-терминах")
    assumptions: list[str] = Field(default_factory=list)
    system_context: SystemContext
    technical_contradiction: str
    physical_contradiction: str
    contradiction_type: str = Field(
        description="техническое | физическое | административное | комбинированное"
    )
    ideal_final_result: str
    analysis: AnalysisBlock
    triz_tools: list[TrizToolRow]
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
