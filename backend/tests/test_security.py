"""Testes de auth (X-API-Key) e rate limit — API antes era 100% aberta."""

import logging

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


async def test_auth_failure_logs_security_event(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """401 deve gerar uma linha dedicada no logger "app.security" (auditável)."""
    monkeypatch.setattr(settings, "API_KEY", "secret123")

    with caplog.at_level(logging.WARNING, logger="app.security"):
        response = await client.get("/v1/datasets")

    assert response.status_code == 401
    assert any("auth failed" in record.message for record in caplog.records)


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


async def test_proxy_headers_ignored_by_default(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem TRUST_PROXY_HEADERS, X-Forwarded-For é ignorado (não é forjável)."""
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    assert settings.TRUST_PROXY_HEADERS is False

    first = await client.get("/v1/datasets", headers={"X-Forwarded-For": "9.9.9.9"})
    second = await client.get("/v1/datasets", headers={"X-Forwarded-For": "8.8.8.8"})

    assert first.status_code == 200
    # Mesma conexão de teste por baixo — XFF diferente não abre bucket novo.
    assert second.status_code == 429


async def test_trust_proxy_headers_splits_bucket_by_xff(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com TRUST_PROXY_HEADERS, cada IP em X-Forwarded-For tem seu próprio bucket."""
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)

    client_a_first = await client.get("/v1/datasets", headers={"X-Forwarded-For": "1.1.1.1"})
    client_b_first = await client.get("/v1/datasets", headers={"X-Forwarded-For": "2.2.2.2"})
    client_a_second = await client.get("/v1/datasets", headers={"X-Forwarded-For": "1.1.1.1"})

    assert client_a_first.status_code == 200
    assert client_b_first.status_code == 200  # IP diferente, bucket próprio
    assert client_a_second.status_code == 429  # mesmo IP do primeiro, já estourou
