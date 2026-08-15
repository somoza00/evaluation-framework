"""Entrypoint da aplicação FastAPI do evaluation-framework."""

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, update

from app.api.v1.datasets import router as datasets_router
from app.api.v1.evaluations import router as evaluations_router
from app.api.v1.results import router as results_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, Base, engine
from app.core.logging import RequestContextMiddleware, configure_logging
from app.core.security import rate_limit, require_api_key
from app.models.evaluation import EvaluationRun, RunStatus

configure_logging()

app = FastAPI(
    title="Evaluation Framework",
    version="0.1.0",
    description="LLM response quality evaluation framework",
)

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# Prefixo /v1 aplicado aqui (os routers não o carregam) — mantém o contrato
# /v1 da API validado na Fase 4 (frontend faz proxy de /v1). Auth (X-API-Key)
# e rate limit são aplicados a todas as rotas /v1 aqui, centralizados.
_v1_dependencies = [Depends(require_api_key), Depends(rate_limit)]
app.include_router(datasets_router, prefix="/v1", dependencies=_v1_dependencies)
app.include_router(evaluations_router, prefix="/v1", dependencies=_v1_dependencies)
app.include_router(results_router, prefix="/v1", dependencies=_v1_dependencies)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check real: falha (503) se o banco não responder.

    Antes retornava {"status": "ok"} sem tocar no banco — um Postgres
    morto ainda passava no healthcheck do orquestrador.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"banco indisponível: {exc}") from exc
    return {"status": "ok"}


async def _recover_orphaned_runs() -> None:
    """Marca como FAILED runs presas em RUNNING num restart do processo.

    O runner roda via BackgroundTasks in-process: se o processo morre no
    meio de uma run, ela fica presa em RUNNING para sempre (nada nunca
    mais atualiza o status). Resultados já persistidos (commit por sample,
    ver runner.py) não são perdidos — só a run é marcada como falha.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.status == RunStatus.RUNNING)
            .values(status=RunStatus.FAILED)
        )
        await session.commit()


@app.on_event("startup")
async def startup() -> None:
    """Cria tabelas em dev (create_all) e recupera runs órfãs em qualquer ambiente.

    Em produção o schema deve vir do `alembic upgrade head` no entrypoint
    do container, não do create_all (ver Dockerfile).
    """
    if settings.APP_ENV != "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await _recover_orphaned_runs()
