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


# --- CORS_ORIGINS: JSON (formato documentado) e lista separada por vírgula ---


def test_cors_origins_aceita_lista_separada_por_virgula(monkeypatch: pytest.MonkeyPatch) -> None:
    """`https://a,https://b` no ambiente não pode derrubar o import do app.

    pydantic-settings decodifica `list[str]` do ambiente como JSON: sem a
    guarda, o `Settings()` do import levantava SettingsError e o container
    morria antes do `/health`.
    """
    monkeypatch.setenv("CORS_ORIGINS", "https://a.pages.dev, https://b.example.com")

    settings = Settings(**_BASE_KWARGS)  # type: ignore[arg-type]

    assert settings.CORS_ORIGINS == ["https://a.pages.dev", "https://b.example.com"]


def test_cors_origins_uma_origem_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uma única origem, sem vírgula, também vira lista (de 1 item)."""
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")

    settings = Settings(**_BASE_KWARGS)  # type: ignore[arg-type]

    assert settings.CORS_ORIGINS == ["https://app.example.com"]


def test_cors_origins_json_continua_funcionando(monkeypatch: pytest.MonkeyPatch) -> None:
    """O formato documentado até agora (JSON) mantém o comportamento."""
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.example.com", "https://b.example.com"]')

    settings = Settings(**_BASE_KWARGS)  # type: ignore[arg-type]

    assert settings.CORS_ORIGINS == ["https://a.example.com", "https://b.example.com"]


def test_cors_origins_vazio_vira_lista_vazia(monkeypatch: pytest.MonkeyPatch) -> None:
    """`CORS_ORIGINS=` (vazio) = nenhuma origem liberada, sem SettingsError."""
    monkeypatch.setenv("CORS_ORIGINS", "")

    settings = Settings(**_BASE_KWARGS)  # type: ignore[arg-type]

    assert settings.CORS_ORIGINS == []
