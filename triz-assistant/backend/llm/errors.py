"""Обработка ошибок OpenAI SDK и валидации в TRIZ LLM-цепочке."""

import logging
from contextlib import contextmanager
from typing import Iterator

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class TRIZChainError(Exception):
    """Ошибка при работе TRIZ LLM-цепочки."""


def _is_chat_operation(operation: str) -> bool:
    return operation == "TRIZChain.chat"


@contextmanager
def wrap_openai_errors(operation: str) -> Iterator[None]:
    """Преобразует исключения OpenAI SDK и ValidationError в TRIZChainError."""
    chat_mode = _is_chat_operation(operation)
    try:
        yield
    except TRIZChainError:
        raise
    except RateLimitError as exc:
        if chat_mode:
            raise TRIZChainError(f"Rate limit: {exc}") from exc
        logger.error("Превышен лимит OpenAI: %s", exc)
        raise TRIZChainError("Превышен лимит запросов OpenAI. Повторите попытку позже.") from exc
    except AuthenticationError as exc:
        if chat_mode:
            raise TRIZChainError("Неверный OPENAI_API_KEY. Обновите ключ в .env.") from exc
        logger.error("Неверный OPENAI_API_KEY: %s", exc)
        raise TRIZChainError(
            "Неверный OPENAI_API_KEY. Создайте новый ключ на "
            "https://platform.openai.com/api-keys и обновите .env."
        ) from exc
    except APIConnectionError as exc:
        if chat_mode:
            raise TRIZChainError(
                "Не удалось подключиться к OpenAI API. Проверьте сеть и прокси."
            ) from exc
        logger.error("Нет соединения с OpenAI: %s", exc)
        detail = str(exc).lower()
        if "timed out" in detail or "timeout" in detail:
            raise TRIZChainError(
                "Таймаут при обращении к OpenAI API. Проверьте прокси "
                "(OPENAI_PROXY_URL) или увеличьте таймаут; без прокси доступ "
                "может быть заблокирован."
            ) from exc
        raise TRIZChainError(
            "Не удалось подключиться к OpenAI API. Проверьте сеть и прокси."
        ) from exc
    except APIStatusError as exc:
        if chat_mode:
            raise TRIZChainError(f"Ошибка OpenAI API: {exc.message}") from exc
        logger.error("Ошибка OpenAI API (статус %s): %s", exc.status_code, exc)
        raise TRIZChainError(f"Ошибка OpenAI API: {exc.message}") from exc
    except ValidationError as exc:
        if chat_mode:
            logger.exception("Ошибка %s", operation)
            raise TRIZChainError(f"Не удалось получить ответ модели: {exc}") from exc
        logger.error("Ошибка валидации core-ответа модели: %s", exc)
        raise TRIZChainError(f"Модель вернула некорректную структуру анализа: {exc}") from exc
    except Exception as exc:
        logger.exception("Ошибка %s", operation)
        raise TRIZChainError(f"Не удалось получить ответ модели: {exc}") from exc
