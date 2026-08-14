"""Entrypoint da aplicação FastAPI do evaluation-framework."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.datasets import router as datasets_router
from app.api.v1.evaluations import router as evaluations_router
from app.api.v1.results import router as results_router
from app.core.config import settings
from app.core.database import Base, engine

app = FastAPI(
    title="Evaluation Framework",
    version="0.1.0",
    description="LLM response quality evaluation framework",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prefixo /v1 aplicado aqui (os routers não o carregam) — mantém o contrato
# /v1 da API validado na Fase 4 (frontend faz proxy de /v1).
app.include_router(datasets_router, prefix="/v1")
app.include_router(evaluations_router, prefix="/v1")
app.include_router(results_router, prefix="/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check simples."""
    return {"status": "ok"}


@app.on_event("startup")
async def startup() -> None:
    """Cria tabelas se não existirem (dev only; em prod usar Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
