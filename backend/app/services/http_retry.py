"""Retry com backoff exponencial para chamadas HTTP ao gateway.

Sem isso, um único 429 (rate limit) ou 5xx transitório do gateway derruba
a sample inteira (e, antes desta mudança, a run inteira). Erros de conexão
(timeout, connection refused) e status 429/5xx são retentados; outros
erros HTTP (4xx que não 429) propagam na primeira tentativa — não faz
sentido re-tentar um 400/401.
"""

import asyncio

import httpx

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


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
        try:
            response = await client.post(url, headers=headers, json=json_body)
        except httpx.TransportError as exc:
            last_exc = exc
        else:
            if response.status_code not in _RETRYABLE_STATUS:
                response.raise_for_status()
                return response
            last_exc = httpx.HTTPStatusError(
                f"status {response.status_code}", request=response.request, response=response
            )

        if attempt < attempts - 1:
            await asyncio.sleep(base_delay * (2**attempt))

    assert last_exc is not None
    raise last_exc
