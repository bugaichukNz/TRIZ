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





class HistoryEntry(BaseModel):

    """Запись истории TRIZ-анализа."""



    id: str

    problem: str

    result: dict = Field(default_factory=dict)

    time: str

    created_at: str | None = None

    chat_session_id: str | None = None





class HistoryEntryCreate(BaseModel):

    """Добавление записи в историю."""



    problem: str = Field(..., min_length=1)

    result: dict

    time: str | None = Field(
        default=None,
        description="Отображаемое время (dd.mm.yyyy HH:MM); если не задано — серверное",
    )





class SessionsListResponse(BaseModel):

    """Список записей истории."""



    items: list[HistoryEntry]

    limit: int





class SessionsReplaceRequest(BaseModel):

    """Полная замена списка истории."""



    items: list[HistoryEntry] = Field(default_factory=list)





class ChatMessage(BaseModel):

    """Сообщение в диалоге интервью."""



    role: str = Field(description="user | assistant")

    content: str





class ChatSessionResponse(BaseModel):

    """Состояние сессии интервью."""



    id: str

    status: str = Field(description="interview | ready | analyzed")

    title: str | None = None

    messages: list[ChatMessage]

    brief: str | None = None

    created_at: str

    updated_at: str





class ChatMessageRequest(BaseModel):

    """Отправка сообщения пользователя."""



    content: str = Field(..., min_length=1, max_length=8000)





class ActiveChatStateResponse(BaseModel):

    """ID активного диалога (хранится в SQLite)."""

    session_id: str | None = None


class ActiveChatStateUpdate(BaseModel):

    session_id: str | None = None


class ChatSessionSummary(BaseModel):

    """Краткая информация о диалоге (без полного списка сообщений)."""

    id: str

    status: str = Field(description="interview | ready | analyzed")

    title: str

    message_count: int

    brief: str | None = None

    created_at: str

    updated_at: str


class ChatSessionsListResponse(BaseModel):

    """Список сохранённых диалогов."""

    items: list[ChatSessionSummary]

    limit: int


class ChatSessionsBulkDeleteRequest(BaseModel):

    """Массовое удаление диалогов по id."""

    ids: list[str] = Field(..., min_length=1)


class ChatSessionsDeleteResponse(BaseModel):

    deleted: int


class ChatAnalyzeResponse(BaseModel):

    """Результат анализа после интервью."""



    session_id: str

    brief: str

    result: SolveResponse


