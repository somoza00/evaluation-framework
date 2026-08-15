"""Autenticação por API key e rate limit em memória para a API pública.

A API hoje é 100% aberta: qualquer um que alcance o backend cria datasets,
dispara runs e gasta tokens reais do gateway. As duas dependências abaixo
fecham isso sem exigir infraestrutura nova (sem Redis, sem serviço extra).
"""

import time
from collections import defaultdict

from fastapi import Header, HTTPException, Request

from app.core.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Valida o header X-API-Key contra settings.API_KEY.

    Se API_KEY não estiver configurada (default, dev), a checagem é pulada
    — ver checklist de produção no README: definir API_KEY é bloqueante
    antes de qualquer deploy real.
    """
    if settings.API_KEY is None:
        return
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=401, detail="X-API-Key inválida ou ausente")


_WINDOW_SECONDS = 60.0
_hits: dict[str, list[float]] = defaultdict(list)


async def rate_limit(request: Request) -> None:
    """Limita requests/minuto por IP (settings.RATE_LIMIT_PER_MINUTE).

    Implementação em memória de um único processo: não substitui um
    limiter compartilhado (Redis, gateway) se a API rodar com múltiplos
    workers/réplicas, mas fecha o caso mais óbvio de abuso hoje.
    """
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    hits = _hits[client_ip]
    cutoff = now - _WINDOW_SECONDS
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=429, detail="rate limit excedido, tente novamente em instantes"
        )
    hits.append(now)
