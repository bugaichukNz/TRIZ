"""Общие фикстуры pytest. Без .env и без сетевых вызовов."""

from __future__ import annotations

import os
from typing import Any

import pytest
from langchain_core.runnables import RunnableLambda

# JWT_SECRET обязателен при импорте backend.config — задаём до любых импортов backend.*
os.environ.setdefault("JWT_SECRET", "pytest-test-jwt-secret-not-for-production")

from backend.config import settings  # noqa: E402


class _FakeStructuredOutput:
    """Обёртка, имитирующая llm.with_structured_output(...).invoke()."""

    def __init__(self, parent: "FakeLLM", model_class: type) -> None:
        self._parent = parent
        self._model_class = model_class

    def invoke(self, _messages: Any) -> Any:
        return self._parent._resolve(self._model_class)


class FakeLLM:
    """
    Подмена LLM-клиента: with_structured_output(...).invoke() возвращает
    заранее заданный ответ (по классу Pydantic-модели или default).
    """

    def __init__(
        self,
        responses: dict[type, Any] | None = None,
        *,
        default: Any = None,
    ) -> None:
        self._responses: dict[type, Any] = dict(responses or {})
        self._default = default

    def _resolve(self, model_class: type) -> Any:
        if model_class in self._responses:
            value = self._responses[model_class]
            if isinstance(value, dict) and hasattr(model_class, "model_validate"):
                return model_class.model_validate(value)
            return value
        if self._default is not None:
            if isinstance(self._default, dict) and hasattr(model_class, "model_validate"):
                return model_class.model_validate(self._default)
            return self._default
        if hasattr(model_class, "model_fields"):
            fields = model_class.model_fields
            kwargs: dict[str, Any] = {}
            for name, field in fields.items():
                annotation = field.annotation
                if annotation is bool:
                    kwargs[name] = True
                elif annotation is str:
                    kwargs[name] = ""
                elif getattr(annotation, "__origin__", None) is list:
                    kwargs[name] = []
            return model_class(**kwargs)
        return {}

    def with_structured_output(self, model_class: type) -> RunnableLambda:
        inner = _FakeStructuredOutput(self, model_class)
        return RunnableLambda(inner.invoke)

    def invoke(self, _messages: Any) -> Any:
        if self._default is not None:
            return self._default
        return {}


@pytest.fixture
def fake_llm():
    """Фабрика FakeLLM: fake_llm({ModelClass: response}) или fake_llm(default=...)."""

    def _factory(
        responses: dict[type, Any] | None = None,
        *,
        default: Any = None,
    ) -> FakeLLM:
        return FakeLLM(responses, default=default)

    return _factory


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тесты не читают .env и не используют реальный OPENAI_API_KEY."""
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "openai_base_url", "")
    monkeypatch.setattr(settings, "openai_proxy_url", "")
    monkeypatch.setattr(
        settings,
        "jwt_secret",
        os.environ["JWT_SECRET"],
    )
    monkeypatch.setattr(settings, "effects_rag_enabled", False)  # изоляция: дефолт True


@pytest.fixture(autouse=True)
def _isolate_app_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Сброс singleton-кешей, solve_jobs и дефолтной БД на tmp_path."""
    from backend.main import app, get_chain, get_chat_store, get_chat_service
    from backend.solve_jobs import solve_jobs

    app.dependency_overrides.clear()
    get_chain.cache_clear()
    get_chat_store.cache_clear()
    get_chat_service.cache_clear()
    solve_jobs.reset()

    db_path = tmp_path / "pytest-isolated.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path.as_posix()}")
