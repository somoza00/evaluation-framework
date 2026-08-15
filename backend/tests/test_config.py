"""Testes do fail-closed: produção não pode subir sem API_KEY."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_BASE_KWARGS = {
    "DATABASE_URL": "sqlite+aiosqlite://",
    "GATEWAY_URL": "http://localhost:8000",
    "GATEWAY_API_KEY": "k",
}


def test_production_without_api_key_raises() -> None:
    """APP_ENV=production + API_KEY ausente deve falhar na instanciação."""
    with pytest.raises(ValidationError, match="API_KEY"):
        Settings(APP_ENV="production", **_BASE_KWARGS)  # type: ignore[arg-type]


def test_production_with_api_key_is_fine() -> None:
    """APP_ENV=production + API_KEY definida sobe normalmente."""
    settings = Settings(APP_ENV="production", API_KEY="secret", **_BASE_KWARGS)  # type: ignore[arg-type]
    assert settings.API_KEY == "secret"


def test_development_without_api_key_is_fine() -> None:
    """Fora de produção, API_KEY continua opcional (auth desabilitada)."""
    settings = Settings(APP_ENV="development", **_BASE_KWARGS)  # type: ignore[arg-type]
    assert settings.API_KEY is None
