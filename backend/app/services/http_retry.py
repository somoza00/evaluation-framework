"""Retry com backoff exponencial para chamadas HTTP ao gateway.

Sem isso, um único 429 (rate limit) ou 5xx transitório do gateway derruba
a sample inteira (e, antes desta mudança, a run inteira). Erros de conexão
(timeout, connection refused) e status 429/5xx são retentados; outros
erros HTTP (4xx que não 429) propagam na primeira tentativa — não faz
sentido re-tentar um 400/401.
"""

import asyncio
import logging
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Teto do intervalo entre tentativas, em segundos. O `Retry-After` vem do
# upstream e não tem limite superior: um proxy devolvendo `Retry-After: 3600`
# (ou uma HTTP-date horas à frente) fazia o worker dormir uma hora no meio da
# run — a run ficava RUNNING, a sample não avançava e o slot de trabalho ficava
# preso, sem erro visível. Acima deste teto é melhor desistir rápido (o erro
# propaga depois das `attempts`) do que dormir por tempo arbitrário.
_MAX_RETRY_DELAY_SECONDS = 30.0


def _parse_retry_after(
    response: httpx.Response, *, now: datetime | None = None
) -> float:
    """Retry-After em segundos do upstream (numérico OU HTTP-date); 0 se inválido/ausente."""
    value = response.headers.get("retry-after")
    if not value:
        return 0.0
    try:
        seconds = float(value)
        # float("inf"), "inf" textual, "1e999" (overflow) ou "nan" do upstream
        # não podem virar asyncio.sleep(<não-finito>) — travaria a sample (e a
        # run inteira, no gather). Trata como "sem Retry-After" (0s).
        return max(0.0, seconds) if math.isfinite(seconds) else 0.0
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        ref = now if now is not None else datetime.now(UTC)
        return max(0.0, (retry_at - ref).total_seconds())
    except (TypeError, ValueError):
        return 0.0


async def post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, object],
    attempts: int = 3,
    base_delay: float = 0.5,
) -> httpx.Response:
    """POST com retry (backoff exponencial) em erro de transporte ou 429/5xx."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        # Zerado a cada tentativa: o Retry-After vale para o response daquela
        # tentativa. Sem o reset, uma tentativa que falhasse por transporte
        # (sem response, logo sem header) herdava o valor da anterior e o sleep
        # repetia uma espera que ninguém pediu — ex.: 429 com `Retry-After: 30`
        # seguido de connection reset dormia 30s de novo, em vez do backoff.
        retry_after_seconds = 0.0
        try:
            response = await client.post(url, headers=headers, json=json_body)
        except httpx.TransportError as exc:
            last_exc = exc
        else:
            if response.status_code not in _RETRYABLE_STATUS:
                response.raise_for_status()
                return response
            # Honra o Retry-After do upstream tanto no 429 quanto num 5xx
            # (ex.: 503 de manutenção/overload do gateway) — o upstream sabe
            # melhor que o nosso backoff exponencial quanto esperar.
            retry_after_seconds = _parse_retry_after(response)
            last_exc = httpx.HTTPStatusError(
                f"status {response.status_code}", request=response.request, response=response
            )

        if attempt < attempts - 1:
            # O teto vale para os dois lados do `max`: um Retry-After absurdo não
            # pode virar uma espera de horas dentro da run.
            backoff = min(
                max(base_delay * (2**attempt), retry_after_seconds),
                _MAX_RETRY_DELAY_SECONDS,
            )
            logger.warning(
                "http retry %d/%d em %.2fs (ultima falha: %s)",
                attempt + 1,
                attempts,
                backoff,
                last_exc,
            )
            await asyncio.sleep(backoff)

    assert last_exc is not None
    raise last_exc
