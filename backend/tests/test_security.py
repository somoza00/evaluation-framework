"""Testes de auth (X-API-Key) e rate limit — API antes era 100% aberta."""

import logging
from collections.abc import Callable
from typing import Self

import pytest
from httpx import AsyncClient
from redis.exceptions import RedisError

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
    # 429 diz ao cliente quanto esperar (janela de 60s), sem adivinhar.
    assert third.headers.get("retry-after") == "60"


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


async def test_rate_limit_bounds_distinct_ips(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rate-limit em memória não cresce sem limite: expulsa o IP mais antigo.

    A API é pública; sem `_MAX_RATE_LIMIT_IPS`, cada IP distinto deixa uma
    entrada residente pra sempre e o processo vaza memória com o tempo.
    """
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 50)
    monkeypatch.setattr(security_module, "_MAX_RATE_LIMIT_IPS", 2)

    for ip in ("1.1.1.1", "2.2.2.2", "3.3.3.3"):
        await client.get("/v1/datasets", headers={"X-Forwarded-For": ip})

    assert "1.1.1.1" not in security_module._hits  # mais antigo foi expulso
    assert "2.2.2.2" in security_module._hits
    assert "3.3.3.3" in security_module._hits


class _FakePipeline:
    """Pipeline mínimo do redis-py async: bufferiza os comandos e aplica no EXECUTE.

    Só o que o limiter usa: `SET key 0 EX <ttl> NX`, `INCR key` e `TTL key`.
    """

    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops: list[Callable[[], object]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    def set(
        self, key: str, value: object, *, ex: int | None = None, nx: bool = False
    ) -> Self:
        self._ops.append(lambda: self._redis.do_set(key, value, ex=ex, nx=nx))
        return self

    def incr(self, key: str) -> Self:
        self._ops.append(lambda: self._redis.do_incr(key))
        return self

    def ttl(self, key: str) -> Self:
        self._ops.append(lambda: self._redis.ttl_of(key))
        return self

    async def execute(self) -> list[object]:
        return [op() for op in self._ops]


class _FakeRedis:
    """Redis em memória com contadores e TTLs, suficiente para o limiter."""

    def __init__(self, *, counts: dict[str, int] | None = None) -> None:
        self.counts: dict[str, int] = dict(counts or {})
        self.ttls: dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)

    def do_set(
        self, key: str, value: object, *, ex: int | None = None, nx: bool = False
    ) -> bool:
        if nx and key in self.counts:
            return False
        self.counts[key] = int(value)  # type: ignore[arg-type]
        if ex is not None:
            self.ttls[key] = ex
        return True

    def do_incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    def ttl_of(self, key: str) -> int:
        """TTL restante em segundos (-1 = chave existe sem expiração, como no Redis)."""
        return self.ttls.get(key, -1)


async def test_shared_rate_limit_counts_in_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Com REDIS_URL, o limite é contado no Redis (compartilhado entre workers)."""
    fake = _FakeRedis()
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(security_module, "_redis_client", fake)
    monkeypatch.setattr(security_module, "_redis_initialized", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 2)

    assert await security_module._shared_rate_limit_exceeded("9.9.9.9") is False
    assert await security_module._shared_rate_limit_exceeded("9.9.9.9") is False
    assert await security_module._shared_rate_limit_exceeded("9.9.9.9") is True
    # A janela é fixa: o TTL da chave é definido na criação e não é renovado
    # a cada request (senão um cliente contínuo nunca sairia do 429).
    assert fake.ttls["ratelimit:9.9.9.9"] == int(security_module._WINDOW_SECONDS)


async def test_shared_rate_limit_always_sets_ttl_on_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regressão: a chave do contador NUNCA nasce sem TTL.

    Antes era `INCR` seguido de `EXPIRE` (só quando o INCR devolvia 1). Se a
    conexão caísse entre os dois comandos — ou o processo morresse num deploy —
    o contador ficava sem TTL e cada request seguinte só somava: o IP era
    bloqueado para sempre, sem nada que expirasse a chave.
    """
    fake = _FakeRedis()
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(security_module, "_redis_client", fake)
    monkeypatch.setattr(security_module, "_redis_initialized", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 10)

    await security_module._shared_rate_limit_exceeded("8.8.8.8")

    assert fake.counts["ratelimit:8.8.8.8"] == 1
    assert fake.ttls["ratelimit:8.8.8.8"] == int(security_module._WINDOW_SECONDS)


async def test_shared_rate_limit_repairs_key_without_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chave órfã sem TTL (criada pela versão anterior) é reparada, não herdada.

    Sem o reparo, um contador antigo sem expiração continuaria bloqueando o IP
    para sempre mesmo depois do deploy da correção.
    """
    fake = _FakeRedis(counts={"ratelimit:7.7.7.7": 5})
    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(security_module, "_redis_client", fake)
    monkeypatch.setattr(security_module, "_redis_initialized", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 100)

    assert await security_module._shared_rate_limit_exceeded("7.7.7.7") is False

    assert fake.counts["ratelimit:7.7.7.7"] == 6  # contador preservado (janela atual)
    assert fake.ttls["ratelimit:7.7.7.7"] == int(security_module._WINDOW_SECONDS)


async def test_shared_rate_limit_falls_back_on_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis indisponível → None, para o chamador cair no limiter local."""

    class BrokenRedis:
        def pipeline(self, transaction: bool = True) -> None:
            raise RedisError("redis down")

    monkeypatch.setattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(security_module, "_redis_client", BrokenRedis())
    monkeypatch.setattr(security_module, "_redis_initialized", True)

    assert await security_module._shared_rate_limit_exceeded("9.9.9.9") is None
