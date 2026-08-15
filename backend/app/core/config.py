"""Configuração central da aplicação via pydantic-settings."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações lidas de variáveis de ambiente ou de backend/.env.

    DATABASE_URL, GATEWAY_URL e GATEWAY_API_KEY são obrigatórias;
    sem elas (ou sem o arquivo .env) a instanciação falha de propósito.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    GATEWAY_URL: str
    GATEWAY_API_KEY: str
    JUDGE_MODEL: str = "deepseek/deepseek-chat"
    APP_ENV: str = "development"
    CORS_ORIGINS: list[str] = ["http://localhost:5174"]

    # Chave de autenticação da própria API (header X-API-Key). None = auth
    # desabilitada (dev). Em produção, defina para fechar a API.
    API_KEY: str | None = None
    # Requests/minuto por IP antes de responder 429 (rate limit simples, em
    # memória — suficiente para um único processo; não substitui um limiter
    # compartilhado se a API rodar com múltiplos workers/réplicas).
    RATE_LIMIT_PER_MINUTE: int = 120
    # Samples processadas em paralelo por run (chamadas ao gateway são
    # I/O-bound; processamento serial era o gargalo de performance).
    RUN_CONCURRENCY: int = 5

    @field_validator("API_KEY", mode="before")
    @classmethod
    def _blank_api_key_means_disabled(cls, value: str | None) -> str | None:
        """`API_KEY=` vazio no .env deve significar "auth desabilitada", não
        uma chave literal de string vazia (que bloquearia toda a API)."""
        return value or None


settings = Settings()  # type: ignore[call-arg]  # campos obrigatórios vêm do ambiente/.env, não de kwargs
