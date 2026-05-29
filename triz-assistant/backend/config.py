"""Централизованная конфигурация приложения из переменных окружения."""



from pydantic_settings import BaseSettings, SettingsConfigDict





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





settings = Settings()


