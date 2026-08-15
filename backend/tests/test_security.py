"""Testes de auth (X-API-Key) e rate limit — API antes era 100% aberta."""

import pytest
from httpx import AsyncClient

import app.core.security as security_module
from app.core.config import settings


@pytest.fixture(autouse=True)
def _clear_rate_limit_state() -> None:
    """_hits é um dict em memória compartilhado entre testes; isola cada teste."""
    security_module._hits.clear()


async def test_api_key_disabled_by_default(client: AsyncClient) -> None:
    """Sem API_KEY configurada (default), a API continua aberta (dev)."""
    assert settings.API_KEY is None
    response = await client.get("/v1/datasets")
    assert response.status_code == 200


async def test_api_key_required_and_enforced(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com API_KEY configurada, requests sem/com a chave errada levam 401."""
    monkeypatch.setattr(settings, "API_KEY", "secret123")

    missing = await client.get("/v1/datasets")
    assert missing.status_code == 401

    wrong = await client.get("/v1/datasets", headers={"X-API-Key": "wrong"})
    assert wrong.status_code == 401

    correct = await client.get("/v1/datasets", headers={"X-API-Key": "secret123"})
    assert correct.status_code == 200


async def test_rate_limit_blocks_after_threshold(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acima de RATE_LIMIT_PER_MINUTE requests/min do mesmo IP, responde 429."""
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)

    first = await client.get("/v1/datasets")
    second = await client.get("/v1/datasets")
    third = await client.get("/v1/datasets")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
