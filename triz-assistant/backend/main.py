"""Точка входа FastAPI для TRIZ AI-ассистента."""



import logging

import time

from functools import lru_cache



from fastapi import Depends, FastAPI, HTTPException, Request

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse



from backend.config import settings

from backend.chat_service import ChatService, ChatServiceError
from backend.chat_store import ChatStore
from backend.llm.chain import TRIZChain, TRIZChainError

from backend.schemas import (
    ActiveChatStateResponse,
    ActiveChatStateUpdate,
    ChatAnalyzeResponse,
    ChatMessage,
    ChatMessageRequest,
    ChatSessionResponse,
    ChatSessionsBulkDeleteRequest,
    ChatSessionsDeleteResponse,
    ChatSessionsListResponse,
    ChatSessionSummary,
    ErrorResponse,
    HealthResponse,
    HistoryEntry,
    HistoryEntryCreate,
    SessionsListResponse,
    SessionsReplaceRequest,
    SolveRequest,
    SolveResponse,
)
from backend.sessions_store import ACTIVE_CHAT_SESSION_KEY, SessionsStore



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",

)

logger = logging.getLogger(__name__)





@lru_cache

def get_chain() -> TRIZChain:

    """Singleton LLM-цепочки."""

    return TRIZChain()


@lru_cache
def get_chat_store() -> ChatStore:
    return ChatStore()


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(get_chat_store(), get_chain())


def get_sessions_store() -> SessionsStore:
    return SessionsStore()


def _clear_active_chat_if_deleted(
    session_ids: list[str],
    sessions_store: SessionsStore,
) -> None:
    active = sessions_store.get_app_state(ACTIVE_CHAT_SESSION_KEY)
    if active and active in session_ids:
        sessions_store.set_app_state(ACTIVE_CHAT_SESSION_KEY, None)


def _session_to_response(session: dict) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session["id"],
        status=session["status"],
        title=session.get("title"),
        messages=[ChatMessage(**m) for m in session["messages"]],
        brief=session.get("brief"),
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )





app = FastAPI(

    title="TRIZ AI Assistant",

    description="API TRIZ-ассистента: экспертный LLM-анализ",

    version="0.2.0",

    responses={

        500: {"model": ErrorResponse},

        502: {"model": ErrorResponse},

    },

)



app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)





@app.middleware("http")

async def log_request_timing(request: Request, call_next):

    """Логирует каждый HTTP-запрос и время выполнения в миллисекундах."""

    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start) * 1000

    logger.info(

        "%s %s -> %s (%.2f ms)",

        request.method,

        request.url.path,

        response.status_code,

        duration_ms,

    )

    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"

    return response





@app.exception_handler(TRIZChainError)

async def triz_error_handler(_request: Request, exc: Exception) -> JSONResponse:

    """Обработчик ошибок TRIZChain."""

    logger.error("TRIZ error: %s", exc)

    return JSONResponse(

        status_code=502,

        content=ErrorResponse(detail=str(exc)).model_dump(),

    )


@app.exception_handler(ChatServiceError)

async def chat_error_handler(_request: Request, exc: Exception) -> JSONResponse:

    logger.warning("Chat error: %s", exc)

    return JSONResponse(

        status_code=400,

        content=ErrorResponse(detail=str(exc)).model_dump(),

    )





@app.get("/", tags=["meta"])

def root() -> dict[str, str]:

    """Информация об API."""

    return {

        "service": "TRIZ AI Assistant",

        "docs": "/docs",

        "health": "/health",

        "solve": "POST /solve",

        "chat": "GET/POST /chat/sessions, DELETE /chat/sessions, POST /chat/sessions/bulk-delete, GET /chat/sessions/{id}, ...",

        "sessions": "GET/POST/PUT/DELETE /sessions",

    }





@app.get("/health", response_model=HealthResponse, tags=["meta"])

def health_check() -> HealthResponse:

    """Статус сервера и конфигурации OpenAI."""

    openai_ok = bool(settings.openai_api_key)

    overall = "ok" if openai_ok else "degraded"

    message = None if openai_ok else "OPENAI_API_KEY не задан в .env"



    return HealthResponse(

        status=overall,

        server="ok",

        llm_model=settings.llm_model,

        openai_configured=openai_ok,

        openai_base_url=settings.openai_base_url or None,

        proxy_enabled=bool(settings.openai_proxy_url),

        message=message,

    )





@app.post(

    "/solve",

    response_model=SolveResponse,

    tags=["triz"],

    summary="Решить TRIZ-задачу",

)

def solve_problem(

    body: SolveRequest,

    chain: TRIZChain = Depends(get_chain),

    store: SessionsStore = Depends(get_sessions_store),

) -> SolveResponse:

    """Экспертный TRIZ-анализ через LLM (результат сохраняется в SQLite)."""

    result = chain.solve(body.problem)

    store.add_entry(body.problem, result)

    return SolveResponse(**result)


@app.get(
    "/chat/sessions",
    response_model=ChatSessionsListResponse,
    tags=["chat"],
    summary="Список сохранённых диалогов",
)
def list_chat_sessions(
    limit: int = 20,
    store: ChatStore = Depends(get_chat_store),
) -> ChatSessionsListResponse:
    cap = max(1, min(limit, 50))
    rows = store.list_sessions(limit=cap)
    items = [ChatSessionSummary(**row) for row in rows]
    return ChatSessionsListResponse(items=items, limit=cap)


@app.post(
    "/chat/sessions",
    response_model=ChatSessionResponse,
    tags=["chat"],
    summary="Новая сессия интервью",
)
def create_chat_session(
    chat: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    session = chat.create_session()
    return _session_to_response(session)


@app.get(
    "/chat/sessions/{session_id}",
    response_model=ChatSessionResponse,
    tags=["chat"],
    summary="Состояние сессии интервью",
)
def get_chat_session(
    session_id: str,
    chat: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    session = chat.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Сессия не найдена.")
    return _session_to_response(session)


@app.delete(
    "/chat/sessions/{session_id}",
    response_model=ChatSessionsDeleteResponse,
    tags=["chat"],
    summary="Удалить диалог",
)
def delete_chat_session(
    session_id: str,
    chat_store: ChatStore = Depends(get_chat_store),
    sessions_store: SessionsStore = Depends(get_sessions_store),
) -> ChatSessionsDeleteResponse:
    deleted = chat_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Сессия не найдена.")
    sessions_store.delete_entries_for_chat_sessions([session_id])
    _clear_active_chat_if_deleted([session_id], sessions_store)
    return ChatSessionsDeleteResponse(deleted=1)


@app.post(
    "/chat/sessions/bulk-delete",
    response_model=ChatSessionsDeleteResponse,
    tags=["chat"],
    summary="Массовое удаление диалогов",
)
def bulk_delete_chat_sessions(
    body: ChatSessionsBulkDeleteRequest,
    chat_store: ChatStore = Depends(get_chat_store),
    sessions_store: SessionsStore = Depends(get_sessions_store),
) -> ChatSessionsDeleteResponse:
    ids = list(dict.fromkeys(body.ids))
    count = chat_store.delete_sessions(ids)
    sessions_store.delete_entries_for_chat_sessions(ids)
    _clear_active_chat_if_deleted(ids, sessions_store)
    return ChatSessionsDeleteResponse(deleted=count)


@app.delete(
    "/chat/sessions",
    response_model=ChatSessionsDeleteResponse,
    tags=["chat"],
    summary="Удалить все диалоги",
)
def delete_all_chat_sessions(
    chat_store: ChatStore = Depends(get_chat_store),
    sessions_store: SessionsStore = Depends(get_sessions_store),
) -> ChatSessionsDeleteResponse:
    rows = chat_store.list_sessions(limit=chat_store.max_sessions)
    ids = [row["id"] for row in rows]
    count = chat_store.delete_all_sessions()
    if ids:
        sessions_store.delete_entries_for_chat_sessions(ids)
    sessions_store.set_app_state(ACTIVE_CHAT_SESSION_KEY, None)
    return ChatSessionsDeleteResponse(deleted=count)


@app.post(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatSessionResponse,
    tags=["chat"],
    summary="Сообщение в интервью",
)
def post_chat_message(
    session_id: str,
    body: ChatMessageRequest,
    chat: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    session = chat.send_message(session_id, body.content)
    return _session_to_response(session)


@app.post(
    "/chat/sessions/{session_id}/complete",
    response_model=ChatSessionResponse,
    tags=["chat"],
    summary="Завершить интервью вручную",
)
def complete_chat_session(
    session_id: str,
    chat: ChatService = Depends(get_chat_service),
) -> ChatSessionResponse:
    session = chat.complete_interview(session_id)
    return _session_to_response(session)


@app.post(
    "/chat/sessions/{session_id}/analyze",
    response_model=ChatAnalyzeResponse,
    tags=["chat"],
    summary="TRIZ-анализ после интервью",
)
def analyze_chat_session(
    session_id: str,
    chat: ChatService = Depends(get_chat_service),
    store: SessionsStore = Depends(get_sessions_store),
) -> ChatAnalyzeResponse:
    result, brief = chat.analyze(session_id)
    store.add_entry(brief, result, chat_session_id=session_id)
    return ChatAnalyzeResponse(
        session_id=session_id,
        brief=brief,
        result=SolveResponse(**result),
    )


@app.get(

    "/sessions",

    response_model=SessionsListResponse,

    tags=["sessions"],

    summary="Список истории анализов",

)

def list_sessions(

    limit: int = 5,

    summary: bool = False,

    store: SessionsStore = Depends(get_sessions_store),

) -> SessionsListResponse:

    """Последние записи истории (новые первыми). summary=true — без тяжёлого result."""

    cap = max(1, min(limit, 20))

    rows = store.list_entries(limit=cap, summary=summary)

    items = [HistoryEntry(**row) for row in rows]

    return SessionsListResponse(items=items, limit=cap)


@app.get(

    "/sessions/{entry_id}",

    response_model=HistoryEntry,

    tags=["sessions"],

    summary="Одна запись истории с полным отчётом",

)

def get_session_entry(

    entry_id: str,

    store: SessionsStore = Depends(get_sessions_store),

) -> HistoryEntry:

    row = store.get_entry(entry_id)

    if row is None:

        raise HTTPException(status_code=404, detail="Запись не найдена.")

    return HistoryEntry(**row)





@app.post(

    "/sessions",

    response_model=HistoryEntry,

    tags=["sessions"],

    summary="Добавить запись в историю",

)

def create_session_entry(

    body: HistoryEntryCreate,

    store: SessionsStore = Depends(get_sessions_store),

) -> HistoryEntry:

    row = store.add_entry(body.problem, body.result, time_display=body.time)

    return HistoryEntry(**row)





@app.put(

    "/sessions",

    response_model=SessionsListResponse,

    tags=["sessions"],

    summary="Заменить весь список истории",

)

def replace_sessions(

    body: SessionsReplaceRequest,

    store: SessionsStore = Depends(get_sessions_store),

) -> SessionsListResponse:

    rows = [item.model_dump() for item in body.items]

    saved = store.replace_all(rows)

    items = [HistoryEntry(**row) for row in saved]

    return SessionsListResponse(items=items, limit=store.max_entries)





@app.delete(

    "/sessions",

    status_code=204,

    tags=["sessions"],

    summary="Очистить историю",

)

def clear_sessions(store: SessionsStore = Depends(get_sessions_store)) -> None:

    store.clear()


@app.get(
    "/state/active-chat",
    response_model=ActiveChatStateResponse,
    tags=["state"],
    summary="Активный диалог (SQLite)",
)
def get_active_chat(
    store: SessionsStore = Depends(get_sessions_store),
) -> ActiveChatStateResponse:
    session_id = store.get_app_state(ACTIVE_CHAT_SESSION_KEY)
    return ActiveChatStateResponse(session_id=session_id)


@app.put(
    "/state/active-chat",
    response_model=ActiveChatStateResponse,
    tags=["state"],
    summary="Установить активный диалог",
)
def set_active_chat(
    body: ActiveChatStateUpdate,
    store: SessionsStore = Depends(get_sessions_store),
) -> ActiveChatStateResponse:
    store.set_app_state(ACTIVE_CHAT_SESSION_KEY, body.session_id)
    return ActiveChatStateResponse(session_id=body.session_id)





if __name__ == "__main__":

    import uvicorn



    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


