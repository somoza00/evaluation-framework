"""Testes dos endpoints de results (médias e ordem do compare)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evaluation import EvaluationResult, EvaluationRun, JudgeType, RunStatus


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


async def test_averages_cover_all_results_not_just_page(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /v1/results/{run_id}?limit=1 calcula médias sobre TODA a run, não só a página."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]

    samples = await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[{"input": f"q{i}", "expected_output": f"a{i}"} for i in range(3)],
    )
    sample_ids = samples.json()["ids"]

    run_id = await _make_run(db_session, dataset_id)

    scores = [0.2, 0.5, 0.8]
    for sid, score in zip(sample_ids, scores):
        db_session.add(
            EvaluationResult(
                run_id=uuid.UUID(run_id),
                sample_id=uuid.UUID(sid),
                actual_output="x",
                score_overall=score,
            )
        )
    await db_session.commit()

    response = await client.get(f"/v1/results/{run_id}", params={"limit": 1})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["count"] == 1  # página de 1
    # Média de toda a run, não da página
    assert body["averages"]["score_overall"] == pytest.approx(sum(scores) / len(scores))


async def test_compare_respects_requested_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """GET /v1/results/compare?runs=B,A,C devolve [B,A,C], na ordem pedida."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]

    run_ids: list[str] = []
    for _ in range(3):
        run_ids.append(await _make_run(db_session, dataset_id))

    requested = [run_ids[1], run_ids[0], run_ids[2]]
    response = await client.get("/v1/results/compare", params={"runs": ",".join(requested)})
    assert response.status_code == 200, response.text
    got = [r["run_id"] for r in response.json()["runs"]]
    assert got == requested