"""Testes do MaxBodySizeMiddleware — não é feito via Pydantic (que só valida
depois do body inteiro lido); precisa cortar a conexão antes disso."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.body_limit import MaxBodySizeMiddleware


async def _echo(request: Request) -> JSONResponse:
    body = await request.body()
    return JSONResponse({"len": len(body)})


def _build_app(max_bytes: int) -> Starlette:
    # Registrado via middleware=[...] (como app.add_middleware faz em
    # main.py) — isso posiciona o middleware DENTRO do ServerErrorMiddleware
    # único da app, igual em produção. Instanciar MaxBodySizeMiddleware
    # manualmente por fora de uma Starlette() já pronta duplicaria o
    # ServerErrorMiddleware e mascararia esse comportamento no teste.
    return Starlette(
        routes=[Route("/echo", _echo, methods=["POST"])],
        middleware=[Middleware(MaxBodySizeMiddleware, max_bytes=max_bytes)],
    )


async def test_allows_body_within_limit() -> None:
    app = _build_app(max_bytes=1_000)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/echo", content=b"x" * 10)
    assert response.status_code == 200
    assert response.json() == {"len": 10}


async def test_rejects_oversized_body_via_content_length() -> None:
    """Body com Content-Length acima do limite é cortado sem nem ser lido."""
    app = _build_app(max_bytes=10)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/echo", content=b"x" * 100)
    assert response.status_code == 413


async def test_rejects_oversized_chunked_body_without_content_length() -> None:
    """Sem Content-Length (chunked), o corte tem que vir da contagem durante o streaming."""

    async def body_gen() -> AsyncIterator[bytes]:
        yield b"x" * 5
        yield b"x" * 5
        yield b"x" * 5  # total 15 > max_bytes=10

    app = _build_app(max_bytes=10)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/echo", content=body_gen())
    assert response.status_code == 413
