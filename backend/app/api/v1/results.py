"""Endpoints de resultados: consulta por run e comparação entre runs."""

import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
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
        run_ids = [uuid.UUID(part.strip()) for part in runs.split(",") if part.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="runs deve conter UUIDs separados por vírgula")
    if not run_ids:
        raise HTTPException(status_code=422, detail="informe ao menos um run_id")

    runs_found = (
        await session.execute(select(EvaluationRun).where(EvaluationRun.id.in_(run_ids)))
    ).scalars().all()
    if len(runs_found) != len(run_ids):
        raise HTTPException(status_code=404, detail="uma ou mais runs não encontradas")

    comparison = []
    for run in runs_found:
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
) -> dict[str, Any]:
    """Retorna todos os EvaluationResults de uma run com médias dos scores."""
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run não encontrada")

    results = (
        await session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run_id))
    ).scalars().all()
    return {
        "run_id": str(run_id),
        "count": len(results),
        "averages": _averages(results),
        "results": [ResultResponse.model_validate(result) for result in results],
    }
