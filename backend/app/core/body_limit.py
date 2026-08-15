"""Limite de tamanho de request body no nível ASGI.

Os limites de campo (Field(max_length=...)) e de itens (Body(max_length=...))
validam DEPOIS que o body inteiro já foi lido para memória — não impedem
por si só um POST de payload gigante de estourar memória antes da
validação rodar. Este middleware corta a conexão antes disso, olhando
Content-Length quando presente e contando bytes durante o streaming
(cobre também o caso de Content-Length ausente/errado).
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    """ASGI puro (não BaseHTTPMiddleware) para interceptar antes do parse do body."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                too_big = int(content_length) > self.max_bytes
            except ValueError:
                too_big = False
            if too_big:
                await _send_413(send)
                return

        seen = 0

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b"") or b"")
                if seen > self.max_bytes:
                    raise _BodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            await _send_413(send)


async def _send_413(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": b'{"detail":"payload muito grande"}'})
