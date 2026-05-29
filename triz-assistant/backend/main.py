"""Точка входа FastAPI для TRIZ AI-ассистента."""



import logging

import time

from functools import lru_cache



from fastapi import Depends, FastAPI, Request

from fastapi.middleware.cors import CORSMiddleware

from fastapi.responses import JSONResponse



from backend.config import settings

from backend.llm.chain import TRIZChain, TRIZChainError

from backend.schemas import ErrorResponse, HealthResponse, SolveRequest, SolveResponse



logging.basicConfig(

    level=logging.INFO,

    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",

)

logger = logging.getLogger(__name__)





@lru_cache

def get_chain() -> TRIZChain:

    """Singleton LLM-цепочки."""

    return TRIZChain()





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





@app.get("/", tags=["meta"])

def root() -> dict[str, str]:

    """Информация об API."""

    return {

        "service": "TRIZ AI Assistant",

        "docs": "/docs",

        "health": "/health",

        "solve": "POST /solve",

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

) -> SolveResponse:

    """Экспертный TRIZ-анализ через LLM."""

    result = chain.solve(body.problem)

    return SolveResponse(**result)





if __name__ == "__main__":

    import uvicorn



    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)


