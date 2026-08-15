"""Autenticação por API key e rate limit em memória para a API pública.

A API hoje é 100% aberta: qualquer um que alcance o backend cria datasets,
dispara runs e gasta tokens reais do gateway. As duas dependências abaixo
fecham isso sem exigir infraestrutura nova (sem Redis, sem serviço extra).
"""

import hmac
import logging
import time
from collections import defaultdict

from fastapi import Header, HTTPException, Request

from app.core.config import settings
from app.core.logging import request_id_var

security_logger = logging.getLogger("app.security")


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


async def rate_limit(request: Request) -> None:
    """Limita requests/minuto por IP (settings.RATE_LIMIT_PER_MINUTE).

    Implementação em memória de um único processo: reinicia com o processo
    e não é compartilhada entre múltiplos workers/réplicas — não é uma
    defesa contra um atacante determinado nesses cenários, só contra abuso
    trivial de um único processo/IP. Um limiter de verdade (Redis) fica
    para quando o deploy realmente tiver mais de um worker.
    """
    client_ip = _client_ip(request)
    now = time.monotonic()
    hits = _hits[client_ip]
    cutoff = now - _WINDOW_SECONDS
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= settings.RATE_LIMIT_PER_MINUTE:
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
            status_code=429, detail="rate limit excedido, tente novamente em instantes"
        )
    hits.append(now)
