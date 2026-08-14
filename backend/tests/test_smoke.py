"""Smoke test: garante que a aplicação importa e expõe a API v1.

Remova/expanda quando os testes reais de cada endpoint forem escritos.
"""

from app.main import app


def test_app_imports() -> None:
    """A app FastAPI carrega com os routers registrados sob /v1."""
    assert app.title == "Evaluation Framework"
    # Usa o schema OpenAPI (estável entre versões do FastAPI) em vez de
    # inspecionar app.routes diretamente — a representação interna de rotas
    # incluídas varia entre versões.
    assert any(path.startswith("/v1") for path in app.openapi()["paths"])
