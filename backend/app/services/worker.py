"""Worker durável: recupera runs PENDING presas (ex.: dispatch perdido num restart).

As runs normais ainda começam pelo `BackgroundTasks` do request (latência baixa).
Este worker é a REDE DE SEGURANÇA: se o processo cair entre criar a run (PENDING)
e o background task executá-la, a run ficaria PENDING para sempre. O worker a
reivindica e executa. `RUN_WORKER_MIN_AGE_SECONDS` evita corrida com o dispatch
imediato (só reivindica PENDING já "velha" o bastante).

Limite conhecido: uma run que ficou RUNNING quando o processo morreu continua
sendo marcada como FAILED pelo sweep de órfãs (`_recover_orphaned_runs`); os
resultados já persistidos por sample não se perdem.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.time import utcnow_naive
from app.models.evaluation import EvaluationRun, RunStatus
from app.services.runner import EvaluationRunner

logger = logging.getLogger("app.worker")


async def claim_next_pending(session: AsyncSession, *, min_age_seconds: int) -> uuid.UUID | None:
    """Reivindica (para RUNNING) a run PENDING mais antiga acima de `min_age_seconds`.

    Retorna o id reivindicado, ou None se não houver run elegível. A
    reivindicação é condicional (`WHERE status = PENDING`) para não roubar uma
    run que já começou a rodar (single-flight entre o worker e o BackgroundTasks).
    """
    cutoff = utcnow_naive() - timedelta(seconds=min_age_seconds)
    run_id = await session.scalar(
        select(EvaluationRun.id)
        .where(EvaluationRun.status == RunStatus.PENDING)
        .where(EvaluationRun.created_at < cutoff)
        .order_by(EvaluationRun.created_at.asc())
        .limit(1)
    )
    if run_id is None:
        return None
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            update(EvaluationRun)
            .where(EvaluationRun.id == run_id, EvaluationRun.status == RunStatus.PENDING)
            .values(status=RunStatus.RUNNING)
        ),
    )
    await session.commit()
    return run_id if result.rowcount == 1 else None


async def _run_claimed(run_id: uuid.UUID) -> None:
    """Executa uma run já reivindicada, com sessão própria (fecha o runner ao fim)."""
    async with AsyncSessionLocal() as session:
        runner = EvaluationRunner(session, settings)
        try:
            await runner.run(run_id)
        finally:
            await runner.close()


async def run_pending_once(*, min_age_seconds: int | None = None) -> bool:
    """Reivindica e executa UMA run PENDING presa. True se executou alguma."""
    if min_age_seconds is None:
        min_age_seconds = settings.RUN_WORKER_MIN_AGE_SECONDS
    async with AsyncSessionLocal() as session:
        run_id = await claim_next_pending(session, min_age_seconds=min_age_seconds)
    if run_id is None:
        return False
    await _run_claimed(run_id)
    return True


async def run_worker_loop() -> None:
    """Loop do worker: reivindica runs PENDING presas e executa. Nunca morre sozinho."""
    poll = settings.RUN_WORKER_POLL_SECONDS
    while True:
        try:
            did_work = await run_pending_once()
        except Exception:
            logger.exception("worker_iteration_failed")
            did_work = False
        if not did_work:
            await asyncio.sleep(poll)
