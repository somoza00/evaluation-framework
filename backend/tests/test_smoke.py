"""Smoke test: garante que a aplicação importa e expõe a API v1.

Remova/expanda quando os testes reais de cada endpoint forem escritos.
"""

from fastapi.middleware.cors import CORSMiddleware

from app.main import app


def test_app_imports() -> None:
    """A app FastAPI carrega com os routers registrados sob /v1."""
    assert app.title == "Evaluation Framework"
    # Usa o schema OpenAPI (estável entre versões do FastAPI) em vez de
    # inspecionar app.routes diretamente — a representação interna de rotas
    # incluídas varia entre versões.
    assert any(path.startswith("/v1") for path in app.openapi()["paths"])


def test_cors_covers_all_api_methods() -> None:
    """Todo método HTTP exposto (GET/POST/DELETE) está liberado no CORS."""
    methods = {m.upper() for p in app.openapi()["paths"].values() for m in p}
    allow = next(
        m.kwargs["allow_methods"] for m in app.user_middleware if m.cls is CORSMiddleware
    )
    assert methods.issubset(set(allow)), methods - set(allow)


async def test_pagination_cap_is_consistent(client) -> None:
    """O teto de página é o mesmo em todos os endpoints (limit > 200 -> 422)."""
    zero = "00000000-0000-0000-0000-000000000000"
    assert (await client.get("/v1/evaluations", params={"limit": 300})).status_code == 422
    assert (await client.get(f"/v1/results/{zero}", params={"limit": 300})).status_code == 422
    assert (
        await client.get(f"/v1/datasets/{zero}/samples", params={"limit": 300})
    ).status_code == 422
