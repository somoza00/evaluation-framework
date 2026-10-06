"""Autenticação por API key e rate limit em memória para a API pública.

A API hoje é 100% aberta: qualquer um que alcance o backend cria datasets,
dispara runs e gasta tokens reais do gateway. As duas dependências abaixo
fecham isso sem exigir infraestrutura nova (sem Redis, sem serviço extra).
"""

import hmac
import logging
import time
from collections import defaultdict

import redis.asyncio as redis_async
from fastapi import Header, HTTPException, Request
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import request_id_var

security_logger = logging.getLogger("app.security")

# Cliente Redis opcional para o rate limit compartilhado (lazy).
_redis_client: redis_async.Redis | None = None
_redis_initialized = False


def _get_redis() -> redis_async.Redis | None:
    """Cliente Redis do rate limit compartilhado, ou None se REDIS_URL não estiver setada."""
    global _redis_client, _redis_initialized
    if not settings.REDIS_URL:
        return None
    if not _redis_initialized:
        _redis_client = redis_async.from_url(settings.REDIS_URL)
        _redis_initialized = True
    return _redis_client


def _client_ip(request: Request) -> str:
    """IP do cliente para fins de rate limit.

    Por padrão usa a conexão TCP direta (request.client.host). Se
    TRUST_PROXY_HEADERS estiver ativa, usa o primeiro IP de
    X-Forwarded-For — só é seguro se a API estiver de fato atrás de um
    proxy confiável que sempre sobrescreve esse header (senão um cliente
    direto forja o header e cada request "vira" um IP diferente).
    """
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def require_api_key(
    request: Request, x_api_key: str | None = Header(default=None)
) -> None:
    """Valida o header X-API-Key contra settings.API_KEY (comparação em
    tempo constante — hmac.compare_digest evita timing attack).

    Se API_KEY não estiver configurada (default, dev), a checagem é pulada.
    Em produção (APP_ENV=production) isso não é possível: Settings recusa
    subir sem API_KEY (ver config.py, fail-closed).
    """
    if settings.API_KEY is None:
        return
    if x_api_key is None or not hmac.compare_digest(x_api_key, settings.API_KEY):
        security_logger.warning(
            "auth failed",
            extra={
                "extra_fields": {
                    "request_id": request_id_var.get(),
                    "ip": _client_ip(request),
                    "path": request.url.path,
                }
            },
        )
        raise HTTPException(status_code=401, detail="X-API-Key inválida ou ausente")


_WINDOW_SECONDS = 60.0
_hits: dict[str, list[float]] = defaultdict(list)

# Teto de IPs distintos rastreados pelo rate-limit em memória. A API é pública
# (Cloud Run, sem auth por padrão); sem um limite, cada IP distinto que fizer
# uma request deixa uma entrada residente pra sempre e o processo cresce sem
# limite. Ao exceder, o bucket mais antigo é expulso (ordem de inserção).
_MAX_RATE_LIMIT_IPS = 10_000


def _reject_rate_limited(client_ip: str, request: Request) -> None:
    """Responde 429 (com Retry-After) e loga o evento no logger app.security."""
    security_logger.warning(
        "rate limit exceeded",
        extra={
            "extra_fields": {
                "request_id": request_id_var.get(),
                "ip": client_ip,
                "path": request.url.path,
            }
        },
    )
    raise HTTPException(
        status_code=429,
        detail="rate limit excedido, tente novamente em instantes",
        headers={"Retry-After": str(int(_WINDOW_SECONDS))},
    )


def _in_memory_rate_limit(client_ip: str) -> bool:
    """Limiter em memória por processo. Retorna True se o limite foi excedido."""
    now = time.monotonic()
    is_new_ip = client_ip not in _hits
    hits = _hits[client_ip]
    cutoff = now - _WINDOW_SECONDS
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= settings.RATE_LIMIT_PER_MINUTE:
        return True
    if is_new_ip and len(_hits) > _MAX_RATE_LIMIT_IPS:
        # Expulsa o bucket mais antigo (dict preserva ordem de inserção): sem
        # isso, um IP que nunca mais volta deixa entrada residente pra sempre
        # e a memória cresce sem limite na API pública.
        _hits.pop(next(iter(_hits)), None)
    hits.append(now)
    return False


async def _shared_rate_limit_exceeded(client_ip: str) -> bool | None:
    """Rate limit compartilhado via Redis (janela fixa). None = desligado/indisponível.

    Com >1 worker/réplica, o limiter em memória por processo não soma os
    contadores; este é compartilhado (contadores no Redis). Se o Redis cair,
    devolve None e o chamador usa o limiter local.
    """
    client = _get_redis()
    if client is None:
        return None
    key = f"ratelimit:{client_ip}"
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, int(_WINDOW_SECONDS))
    except RedisError:
        security_logger.warning(
            "rate_limit_redis_unavailable", extra={"extra_fields": {"ip": client_ip}}
        )
        return None
    return int(count) > settings.RATE_LIMIT_PER_MINUTE


async def rate_limit(request: Request) -> None:
    """Limita requests/minuto por IP (settings.RATE_LIMIT_PER_MINUTE).

    Usa o limiter compartilhado (Redis) quando REDIS_URL está configurada —
    contadores somados entre workers/réplicas. Sem Redis (ou se ele cair), cai
    no limiter em memória por processo (best-effort local).
    """
    client_ip = _client_ip(request)
    shared = await _shared_rate_limit_exceeded(client_ip)
    exceeded = _in_memory_rate_limit(client_ip) if shared is None else shared
    if exceeded:
        _reject_rate_limited(client_ip, request)
