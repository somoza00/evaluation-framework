"""Testes do worker durável: reivindicação de runs PENDING presas."""

import uuid
from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow_naive
from app.models.evaluation import EvaluationRun, JudgeType, RunStatus
from app.services.worker import claim_next_pending


async def test_claim_next_pending_claims_only_old_pending(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Só reivindica PENDING antiga o bastante (evita corrida com o BackgroundTasks)."""
    dataset_id = (await client.post("/v1/datasets", json={"name": "ds"})).json()["id"]
    old_id, fresh_id = uuid.UUID(int=101), uuid.UUID(int=102)
    now = utcnow_naive()
    db_session.add(
        EvaluationRun(
            id=old_id,
            dataset_id=uuid.UUID(dataset_id),
            model="m",
            judge_type=JudgeType.DETERMINISTIC,
            status=RunStatus.PENDING,
            created_at=now - timedelta(seconds=120),
        )
    )
    db_session.add(
        EvaluationRun(
            id=fresh_id,
            dataset_id=uuid.UUID(dataset_id),
            model="m",
            judge_type=JudgeType.DETERMINISTIC,
            status=RunStatus.PENDING,
            created_at=now,
        )
    )
    await db_session.commit()

    claimed = await claim_next_pending(db_session, min_age_seconds=30)

    assert claimed == old_id  # a antiga foi reivindicada (virou RUNNING)
    assert await claim_next_pending(db_session, min_age_seconds=30) is None  # a fresca não


async def test_claim_next_pending_ignores_non_pending(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """RUNNING/DONE/FAILED não são reivindicáveis — só PENDING."""
    dataset_id = (await client.post("/v1/datasets", json={"name": "ds"})).json()["id"]
    old = utcnow_naive() - timedelta(seconds=600)
    for status in (RunStatus.RUNNING, RunStatus.DONE, RunStatus.FAILED):
        db_session.add(
            EvaluationRun(
                id=uuid.uuid4(),
                dataset_id=uuid.UUID(dataset_id),
                model="m",
                judge_type=JudgeType.DETERMINISTIC,
                status=status,
                created_at=old,
            )
        )
    await db_session.commit()

    assert await claim_next_pending(db_session, min_age_seconds=30) is None
