"""Testes do endpoint de results: dedupe de run_ids no compare."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvaluationRun, JudgeType, RunStatus


async def _make_run(db_session: AsyncSession, dataset_id: str) -> str:
    """Insere uma EvaluationRun direto no banco (sem disparar o runner)."""
    run_id = uuid.uuid4()
    db_session.add(
        EvaluationRun(
            id=run_id,
            dataset_id=uuid.UUID(dataset_id),
            model="m",
            judge_type=JudgeType.DETERMINISTIC,
            status=RunStatus.DONE,
        )
    )
    await db_session.commit()
    return str(run_id)


async def test_compare_deduplicates_duplicate_run_ids(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """runs=<id>,<id> não deve dar 404 falso: IDs duplicados são despulados."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]
    run_id = await _make_run(db_session, dataset_id)

    response = await client.get("/v1/results/compare", params={"runs": f"{run_id},{run_id}"})
    assert response.status_code == 200, response.text
    got = [r["run_id"] for r in response.json()["runs"]]
    assert got == [run_id]