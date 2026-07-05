"""Централизованная конфигурация приложения из переменных окружения."""

from typing import Self

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_FORBIDDEN_JWT_SECRET = "triz-dev-secret-change-in-production"
_JWT_SECRET_ERROR = 'Задайте JWT_SECRET в .env (сгенерируйте: python -c "import secrets; print(secrets.token_hex(32))")'


class Settings(BaseSettings):
    """Настройки TRIZ-ассистента. Значения читаются из .env автоматически."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_proxy_url: str = ""
    llm_model: str = "gpt-4o-mini"
    database_url: str = "sqlite:///data/sessions/triz.db"
    history_max_entries: int = 20
    chat_sessions_max: int = 50
    jwt_secret: str
    seed_default_user: bool = False
    default_user_password: str = ""
    effects_rag_enabled: bool = True
    effects_score_threshold: float = 0.40

    @model_validator(mode="after")
    def validate_jwt_secret(self) -> Self:
        if not self.jwt_secret.strip() or self.jwt_secret == _FORBIDDEN_JWT_SECRET:
            raise RuntimeError(_JWT_SECRET_ERROR)
        return self


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        for err in exc.errors():
            if err.get("loc") == ("jwt_secret",):
                raise RuntimeError(_JWT_SECRET_ERROR) from exc
        raise


settings = _load_settings()
