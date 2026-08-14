"""Testes dos endpoints de evaluations (runner mockado, sem HTTP real)."""

import uuid

import pytest
from httpx import AsyncClient

import app.api.v1.evaluations as evaluations_module


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
