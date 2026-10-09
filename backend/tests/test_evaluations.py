"""Testes dos endpoints de evaluations (runner mockado, sem HTTP real)."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

import app.api.v1.evaluations as evaluations_module
from app.models.evaluation import EvaluationRun, JudgeType, RunStatus


@pytest.fixture
def mock_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Substitui o background runner para evitar gateway/banco reais."""

    async def fake_run(run_id: uuid.UUID) -> None:
        """No-op: a run fica em PENDING (sem chamadas externas)."""

    monkeypatch.setattr(evaluations_module, "_run_background", fake_run)


async def _create_dataset(client: AsyncClient) -> str:
    response = await client.post("/v1/datasets", json={"name": "ds-teste", "description": ""})
    assert response.status_code == 201
    return str(response.json()["id"])


async def test_create_evaluation(client: AsyncClient, mock_runner: None) -> None:
    """POST /v1/evaluations retorna 202 com status=pending."""
    dataset_id = await _create_dataset(client)
    response = await client.post(
        "/v1/evaluations",
        json={
            "dataset_id": dataset_id,
            "model": "deepseek/deepseek-chat",
            "judge_type": "llm",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert data["progress"] == 0.0


async def test_list_evaluations(client: AsyncClient, mock_runner: None) -> None:
    """GET /v1/evaluations retorna lista com a run criada."""
    dataset_id = await _create_dataset(client)
    await client.post(
        "/v1/evaluations",
        json={"dataset_id": dataset_id, "model": "m", "judge_type": "deterministic"},
    )

    response = await client.get("/v1/evaluations")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "pending"
    assert runs[0]["progress"] == 0.0


async def test_get_evaluation_status(client: AsyncClient, mock_runner: None) -> None:
    """GET /v1/evaluations/{id} retorna progresso."""
    dataset_id = await _create_dataset(client)
    created = await client.post(
        "/v1/evaluations",
        json={"dataset_id": dataset_id, "model": "m", "judge_type": "llm"},
    )
    run_id = created.json()["id"]

    response = await client.get(f"/v1/evaluations/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run_id
    assert data["status"] == "pending"
    assert data["progress"] == 0.0


async def test_get_results_pagination_shape(client: AsyncClient, mock_runner: None) -> None:
    """GET /v1/results/{run_id} retorna shape paginado (total/limit/offset/count)."""
    dataset_id = await _create_dataset(client)
    created = await client.post(
        "/v1/evaluations",
        json={"dataset_id": dataset_id, "model": "m", "judge_type": "deterministic"},
    )
    run_id = created.json()["id"]

    response = await client.get(
        f"/v1/results/{run_id}", params={"limit": 10, "offset": 0}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == run_id
    assert body["total"] == 0
    assert body["count"] == 0
    assert body["limit"] == 10
    assert body["offset"] == 0
    assert body["results"] == []
    assert body["averages"]["score_overall"] is None


async def test_get_results_invalid_limit_422(client: AsyncClient, mock_runner: None) -> None:
    """limit acima do teto é rejeitado (422)."""
    dataset_id = await _create_dataset(client)
    created = await client.post(
        "/v1/evaluations",
        json={"dataset_id": dataset_id, "model": "m", "judge_type": "deterministic"},
    )
    run_id = created.json()["id"]

    response = await client.get(f"/v1/results/{run_id}", params={"limit": 9999})
    assert response.status_code == 422


async def test_delete_evaluation_removes_run(client: AsyncClient, mock_runner: None) -> None:
    """DELETE /v1/evaluations/{id} remove a run."""
    dataset_id = await _create_dataset(client)
    created = await client.post(
        "/v1/evaluations",
        json={"dataset_id": dataset_id, "model": "m", "judge_type": "deterministic"},
    )
    run_id = created.json()["id"]

    resp = await client.delete(f"/v1/evaluations/{run_id}")
    assert resp.status_code == 204

    listing = (await client.get("/v1/evaluations")).json()
    assert all(r["id"] != run_id for r in listing)


async def test_delete_evaluation_404_when_missing(client: AsyncClient, mock_runner: None) -> None:
    """DELETE /v1/evaluations/{id_inexistente} retorna 404."""
    response = await client.delete(f"/v1/evaluations/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_list_evaluations_stable_tiebreak(
    client: AsyncClient, db_session, mock_runner: None
) -> None:
    """Mesmo created_at: desempate por id desc (ordem total p/ paginação estável)."""
    ds = (await client.post("/v1/datasets", json={"name": "ds"})).json()["id"]
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    low, high = uuid.UUID(int=1), uuid.UUID(int=2)
    for uid in (low, high):
        db_session.add(
            EvaluationRun(
                id=uid, dataset_id=uuid.UUID(ds), model="m",
                judge_type=JudgeType.DETERMINISTIC, created_at=ts,
            )
        )
    await db_session.commit()
    ids = [r["id"] for r in (await client.get("/v1/evaluations")).json()]
    assert ids == [str(high), str(low)]


async def test_list_evaluations_filters_by_status(
    client: AsyncClient, db_session, mock_runner: None
) -> None:
    """`?status=done` retorna só as runs com esse status."""
    ds = (await client.post("/v1/datasets", json={"name": "ds"})).json()["id"]
    done_id, failed_id = uuid.UUID(int=3), uuid.UUID(int=4)
    db_session.add(
        EvaluationRun(
            id=done_id, dataset_id=uuid.UUID(ds), model="m",
            judge_type=JudgeType.DETERMINISTIC, status=RunStatus.DONE,
        )
    )
    db_session.add(
        EvaluationRun(
            id=failed_id, dataset_id=uuid.UUID(ds), model="m",
            judge_type=JudgeType.DETERMINISTIC, status=RunStatus.FAILED,
        )
    )
    await db_session.commit()

    filtered = (await client.get("/v1/evaluations", params={"status": "done"})).json()
    assert [r["id"] for r in filtered] == [str(done_id)]

    all_runs = (await client.get("/v1/evaluations")).json()
    assert {r["id"] for r in all_runs} == {str(done_id), str(failed_id)}


async def test_list_evaluations_filters_by_model(
    client: AsyncClient, db_session, mock_runner: None
) -> None:
    """`?model=` retorna só as runs daquele modelo; ausência do filtro devolve todas."""
    ds = (await client.post("/v1/datasets", json={"name": "ds"})).json()["id"]
    ds_id = uuid.UUID(ds)
    a_id, b_id = uuid.UUID(int=5), uuid.UUID(int=6)
    db_session.add(
        EvaluationRun(
            id=a_id, dataset_id=ds_id, model="deepseek/deepseek-chat",
            judge_type=JudgeType.DETERMINISTIC,
        )
    )
    db_session.add(
        EvaluationRun(
            id=b_id, dataset_id=ds_id, model="openai/gpt-4o",
            judge_type=JudgeType.DETERMINISTIC,
        )
    )
    await db_session.commit()

    filtered = (
        await client.get("/v1/evaluations", params={"model": "deepseek/deepseek-chat"})
    ).json()
    assert [r["id"] for r in filtered] == [str(a_id)]

    all_runs = (await client.get("/v1/evaluations")).json()
    assert {r["id"] for r in all_runs} == {str(a_id), str(b_id)}
