"""Pydantic-модели запросов и ответов API."""



from pydantic import BaseModel, Field



from backend.llm.models import (

    AnalysisBlock,

    FinalConclusionBlock,

    RecommendationsBlock,

    SolutionConcept,

    SystemContext,

    TrizToolRow,

)





class SolveRequest(BaseModel):

    """Запрос на решение TRIZ-задачи."""



    problem: str = Field(

        ...,

        min_length=3,

        description="Текст инженерной или организационной задачи",

        examples=["Нужно уменьшить вес корпуса, сохранив прочность"],

    )





class SolveResponse(BaseModel):

    """Экспертный TRIZ-отчёт + поля обратной совместимости."""



    problem_description: str

    assumptions: list[str] = Field(default_factory=list)

    system_context: SystemContext

    technical_contradiction: str

    physical_contradiction: str

    contradiction_type: str

    ideal_final_result: str

    analysis: AnalysisBlock

    triz_tools: list[TrizToolRow]

    solution_concepts: list[SolutionConcept]

    recommendations: RecommendationsBlock

    final_conclusion: FinalConclusionBlock

    recommended_principles: list[str]

    executive_summary: str

    contradiction: str

    solutions: list[str]

    reasoning: str





class HealthResponse(BaseModel):

    """Статус сервера и LLM."""



    status: str = Field(description="ok | degraded")

    server: str

    llm_model: str

    openai_configured: bool

    openai_base_url: str | None = None

    proxy_enabled: bool = False

    message: str | None = None





class ErrorResponse(BaseModel):

    """Стандартное сообщение об ошибке."""



    detail: str


