"""Testes do helper de retry com backoff usado pelas chamadas ao gateway."""

import logging

import httpx
import pytest

from app.services.http_retry import post_with_retry


async def test_retries_on_429_then_succeeds() -> None:
    """Um 429 seguido de sucesso deve retornar a resposta bem-sucedida."""
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        response = await post_with_retry(
            client, "/x", headers={}, json_body={}, base_delay=0.001
        )
    assert response.status_code == 200
    assert calls["n"] == 3


async def test_raises_after_exhausting_attempts() -> None:
    """5xx persistente deve propagar HTTPStatusError após esgotar as tentativas."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await post_with_retry(
                client, "/x", headers={}, json_body={}, attempts=2, base_delay=0.001
            )


async def test_does_not_retry_non_retryable_client_error() -> None:
    """400 não é transitório: não faz sentido re-tentar, deve propagar na 1a tentativa."""
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await post_with_retry(client, "/x", headers={}, json_body={}, base_delay=0.001)
    assert calls["n"] == 1


async def test_logs_warning_on_retry(caplog: pytest.LogCaptureFixture) -> None:
    """Cada tentativa de retry deve gerar um log de aviso (observabilidade)."""
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"ok": True})

    with caplog.at_level(logging.WARNING, logger="app.services.http_retry"):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://test"
        ) as client:
            await post_with_retry(client, "/x", headers={}, json_body={}, base_delay=0.001)

    assert any("http retry" in r.message for r in caplog.records)
