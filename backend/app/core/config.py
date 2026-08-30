"""Configuração central da aplicação via pydantic-settings."""

from pydantic import field_validator, model_validator
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
    # No startup, runs presas em RUNNING só são marcadas como FAILED se
    # mais antigas que isto (segundos). Evita que um deploy rolling marque
    # como falha uma run ainda ativa na instância anterior.
    ORPHANED_RUN_MAX_AGE_SECONDS: int = 300
    # Confia no header X-Forwarded-For para extrair o IP real do cliente no
    # rate limit. Só ative se a API estiver de fato atrás de um proxy que
    # SEMPRE sobrescreve esse header (Traefik/nginx) — sem isso, um cliente
    # direto pode forjar o header e furar o rate limit por IP.
    TRUST_PROXY_HEADERS: bool = False
    # Corpo de request além disso é rejeitado (413) antes de ser lido por
    # completo — Pydantic só valida depois do body inteiro bufferizado, o
    # que por si só não impede o consumo de memória. Default folgado o
    # bastante para o maior POST /samples legítimo (500 samples x ~40KB).
    MAX_REQUEST_BODY_BYTES: int = 25_000_000

    @field_validator("API_KEY", mode="before")
    @classmethod
    def _blank_api_key_means_disabled(cls, value: str | None) -> str | None:
        """`API_KEY=` vazio no .env deve significar "auth desabilitada", não
        uma chave literal de string vazia (que bloquearia toda a API)."""
        return value or None

    @model_validator(mode="after")
    def _api_key_required_in_production(self) -> "Settings":
        """Fail-closed: em produção, subir sem API_KEY é um deploy aberto por
        acidente — melhor o processo nem iniciar do que servir sem auth."""
        if self.APP_ENV == "production" and self.API_KEY is None:
            raise ValueError(
                "APP_ENV=production exige API_KEY definida "
                "(auth da API não pode ficar desabilitada em produção)"
            )
        return self


settings = Settings()  # type: ignore[call-arg]  # campos obrigatórios vêm do ambiente/.env, não de kwargs
