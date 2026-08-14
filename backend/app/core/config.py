"""Configuração central da aplicação via pydantic-settings."""

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


settings = Settings()  # type: ignore[call-arg]  # campos obrigatórios vêm do ambiente/.env, não de kwargs
