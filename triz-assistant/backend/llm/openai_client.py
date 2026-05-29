"""Фабрика ChatOpenAI с поддержкой base URL и HTTP-прокси."""



import httpx

from langchain_openai import ChatOpenAI



from backend.config import settings





def create_chat_llm(*, temperature: float = 0.25) -> ChatOpenAI:

    """Создаёт LLM-клиент с учётом OPENAI_BASE_URL и OPENAI_PROXY_URL."""

    kwargs: dict = {

        "model": settings.llm_model,

        "api_key": settings.openai_api_key,

        "temperature": temperature,

    }



    if settings.openai_base_url:

        kwargs["base_url"] = settings.openai_base_url



    if settings.openai_proxy_url:

        kwargs["http_client"] = httpx.Client(proxy=settings.openai_proxy_url)

        kwargs["http_async_client"] = httpx.AsyncClient(

            proxy=settings.openai_proxy_url

        )



    return ChatOpenAI(**kwargs)


