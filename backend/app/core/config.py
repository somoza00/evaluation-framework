"""Configuração central da aplicação (pydantic-settings)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações lidas de variáveis de ambiente ou de backend/.env.

    Defaults existem apenas para dev local; em produção os valores
    vêm do ambiente (docker-compose, CI, etc).
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql+asyncpg://eval:eval@localhost:5432/evaluation"
    gateway_url: str = "http://localhost:8000"
    gateway_api_key: str = "sk-local"
    judge_model: str = "deepseek/deepseek-chat"


settings = Settings()
