"""Endpoints de avaliações: criação (background), listagem e detalhe de runs."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_session
from app.models.dataset import Dataset, Sample
from app.models.evaluation import (
    EvaluationResult,
    EvaluationRun,
    JudgeType,
    RunStatus,
)
from app.services.runner import EvaluationRunner

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class EvaluationCreate(BaseModel):
    """Body do POST /v1/evaluations."""

    dataset_id: uuid.UUID
    model: str
    judge_type: JudgeType


class RunResponse(BaseModel):
    """Resposta de run (progress preenchido manualmente)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dataset_id: uuid.UUID
    model: str
    judge_type: JudgeType
    status: RunStatus
    created_at: datetime
    finished_at: datetime | None
    progress: float = 0.0  # 0.0–1.0


def _progress(samples_count: int, results_count: int) -> float:
    """Progresso da run: results/samples (0.0 se não houver samples)."""
    if samples_count == 0:
        return 0.0
    return min(1.0, results_count / samples_count)


async def _run_background(run_id: uuid.UUID) -> None:
    """Executa a run em background com sessão própria (a do request já fechou)."""
    async with AsyncSessionLocal() as session:
        runner = EvaluationRunner(session, settings)
        try:
            await runner.run(run_id)
        finally:
            # Sem isso, o httpx.AsyncClient do LLMJudge vaza uma conexão
            # a cada run (confirmado com ResourceWarning em teste E2E).
            await runner.close()


@router.post("", status_code=202, response_model=RunResponse)
async def create_evaluation(
    payload: EvaluationCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    """Cria uma EvaluationRun (status=PENDING) e dispara o runner em background."""
    dataset = await session.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset não encontrado")

    run = EvaluationRun(
        dataset_id=payload.dataset_id,
        model=payload.model,
        judge_type=payload.judge_type,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    background_tasks.add_task(_run_background, run.id)
    return RunResponse(
        id=run.id,
        dataset_id=run.dataset_id,
        model=run.model,
        judge_type=run.judge_type,
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
        progress=0.0,
    )


@router.get("", response_model=list[RunResponse])
async def list_evaluations(
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = _DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_session),
) -> list[RunResponse]:
    """Lista runs com progresso (results_count / samples_count), paginado."""
    samples_sq = (
        select(func.count(Sample.id))
        .where(Sample.dataset_id == EvaluationRun.dataset_id)
        .correlate(EvaluationRun)
        .scalar_subquery()
    )
    results_sq = (
        select(func.count(EvaluationResult.id))
        .where(EvaluationResult.run_id == EvaluationRun.id)
        .correlate(EvaluationRun)
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(
                EvaluationRun,
                samples_sq.label("samples_count"),
                results_sq.label("results_count"),
            )
            .order_by(EvaluationRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        RunResponse(
            id=run.id,
            dataset_id=run.dataset_id,
            model=run.model,
            judge_type=run.judge_type,
            status=run.status,
            created_at=run.created_at,
            finished_at=run.finished_at,
            progress=_progress(samples, results),
        )
        for run, samples, results in rows
    ]


@router.get("/{run_id}", response_model=RunResponse)
async def get_evaluation(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RunResponse:
    """Retorna uma run específica com progresso detalhado."""
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run não encontrada")

    samples = await session.scalar(
        select(func.count(Sample.id)).where(Sample.dataset_id == run.dataset_id)
    )
    results = await session.scalar(
        select(func.count(EvaluationResult.id)).where(EvaluationResult.run_id == run.id)
    )
    return RunResponse(
        id=run.id,
        dataset_id=run.dataset_id,
        model=run.model,
        judge_type=run.judge_type,
        status=run.status,
        created_at=run.created_at,
        finished_at=run.finished_at,
        progress=_progress(samples or 0, results or 0),
    )
