"""Endpoints de resultados: consulta por run e comparação entre runs."""

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.evaluation import EvaluationResult, EvaluationRun

router = APIRouter(prefix="/results", tags=["results"])

_SCORE_FIELDS = ("score_fidelity", "score_coherence", "score_instruction", "score_overall")


class ResultResponse(BaseModel):
    """Resposta de um EvaluationResult."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sample_id: uuid.UUID
    actual_output: str
    score_fidelity: float | None
    score_coherence: float | None
    score_instruction: float | None
    score_overall: float | None
    judge_reasoning: str | None


def _averages(results: Sequence[EvaluationResult]) -> dict[str, float | None]:
    """Média de cada score sobre os valores não-None (None se vazio)."""
    averages: dict[str, float | None] = {}
    for field in _SCORE_FIELDS:
        values = [getattr(result, field) for result in results if getattr(result, field) is not None]
        averages[field] = sum(values) / len(values) if values else None
    return averages


# Ordem importa: /compare é rota estática e precisa vir antes de /{run_id}.
@router.get("/compare")
async def compare_results(
    runs: str = Query(..., description="IDs de runs separados por vírgula (ex: 1,2,3)"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compara médias de score entre múltiplas runs (side-by-side)."""
    try:
        seen: set[uuid.UUID] = set()
        run_ids: list[uuid.UUID] = []
        for part in runs.split(","):
            part = part.strip()
            if not part:
                continue
            uid = uuid.UUID(part)
            if uid not in seen:
                seen.add(uid)
                run_ids.append(uid)
    except ValueError:
        raise HTTPException(status_code=422, detail="runs deve conter UUIDs separados por vírgula")
    if not run_ids:
        raise HTTPException(status_code=422, detail="informe ao menos um run_id")

    runs_found = (
        await session.execute(select(EvaluationRun).where(EvaluationRun.id.in_(run_ids)))
    ).scalars().all()
    if len(runs_found) != len(run_ids):
        raise HTTPException(status_code=404, detail="uma ou mais runs não encontradas")

    # Respeita a ordem pedida pelo client (runs=B,A,C => resposta [B,A,C]),
    # em vez da ordem do banco (por inserção), para o side-by-side não desalinhar.
    runs_by_id = {run.id: run for run in runs_found}
    comparison = []
    for run in (runs_by_id[run_id] for run_id in run_ids):
        results = (
            await session.execute(
                select(EvaluationResult).where(EvaluationResult.run_id == run.id)
            )
        ).scalars().all()
        comparison.append(
            {
                "run_id": str(run.id),
                "model": run.model,
                "judge_type": run.judge_type.value,
                "status": run.status.value,
                "averages": _averages(results),
            }
        )
    return {"runs": comparison}


@router.get("/{run_id}")
async def get_results(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=500, description="Máx. de resultados por página."),
    offset: int = Query(default=0, ge=0, description="Pula resultados no início."),
) -> dict[str, Any]:
    """Retorna EvaluationResults de uma run, paginado (limit/offset), com médias dos scores."""
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run não encontrada")

    total = (
        await session.execute(
            select(func.count())
            .select_from(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
        )
    ).scalar_one()

    results = (
        await session.execute(
            select(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
            .order_by(EvaluationResult.id)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    # Médias sobre TODOS os resultados da run (não só a página): senão páginas
    # diferentes mostram médias diferentes e divergem de /compare.
    all_results = (
        await session.execute(
            select(EvaluationResult).where(EvaluationResult.run_id == run_id)
        )
    ).scalars().all()
    return {
        "run_id": str(run_id),
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "averages": _averages(all_results),
        "results": [ResultResponse.model_validate(result) for result in results],
    }
