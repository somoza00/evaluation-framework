"""Testes dos endpoints de datasets."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Sample
from app.models.evaluation import EvaluationRun, JudgeType, RunStatus


async def test_create_dataset(client: AsyncClient) -> None:
    """POST /v1/datasets retorna 201 com id e name."""
    response = await client.post(
        "/v1/datasets", json={"name": "meu dataset", "description": "descricao"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "meu dataset"
    assert uuid.UUID(data["id"])  # id é UUID válido


async def test_create_dataset_rejects_blank_name(client: AsyncClient) -> None:
    """POST /v1/datasets com name vazio ou só espaços é rejeitado (422)."""
    resp = await client.post("/v1/datasets", json={"name": "   ", "description": ""})
    assert resp.status_code == 422


async def test_add_samples_rejects_blank_input(client: AsyncClient) -> None:
    """Sample com input só de espaços é rejeitado (422) — não corrompe médias."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]
    resp = await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[{"input": "   ", "expected_output": "a1"}],
    )
    assert resp.status_code == 422


async def test_list_datasets(client: AsyncClient) -> None:
    """GET /v1/datasets retorna lista com os datasets criados."""
    await client.post("/v1/datasets", json={"name": "ds-um", "description": ""})
    await client.post("/v1/datasets", json={"name": "ds-dois", "description": ""})

    response = await client.get("/v1/datasets")
    assert response.status_code == 200
    datasets = response.json()
    assert len(datasets) == 2
    assert {d["name"] for d in datasets} == {"ds-um", "ds-dois"}
    assert all(d["samples_count"] == 0 for d in datasets)


async def test_add_samples_bulk(client: AsyncClient) -> None:
    """POST /v1/datasets/{id}/samples com 3 samples retorna count=3."""
    created = await client.post("/v1/datasets", json={"name": "ds-samples", "description": ""})
    dataset_id = created.json()["id"]

    samples = [
        {"input": f"pergunta {i}", "expected_output": f"resposta {i}", "metadata": {"i": i}}
        for i in range(3)
    ]
    response = await client.post(f"/v1/datasets/{dataset_id}/samples", json=samples)
    assert response.status_code == 201
    data = response.json()
    assert data["count"] == 3
    assert len(data["ids"]) == 3


async def test_dataset_not_found(client: AsyncClient) -> None:
    """GET /v1/datasets/{id_inexistente} retorna 404."""
    response = await client.get(f"/v1/datasets/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_delete_dataset_removes_dataset_and_samples(client: AsyncClient) -> None:
    """DELETE /v1/datasets/{id} remove o dataset e seus samples."""
    created = await client.post("/v1/datasets", json={"name": "para-deletar", "description": ""})
    dataset_id = created.json()["id"]

    await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[{"input": "q1", "expected_output": "a1"}],
    )

    resp = await client.delete(f"/v1/datasets/{dataset_id}")
    assert resp.status_code == 204

    listing = (await client.get("/v1/datasets")).json()
    assert all(d["id"] != dataset_id for d in listing)


async def test_delete_dataset_404_when_missing(client: AsyncClient) -> None:
    """DELETE /v1/datasets/{id_inexistente} retorna 404."""
    response = await client.delete(f"/v1/datasets/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_delete_dataset_409_when_has_runs(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """DELETE /v1/datasets/{id} com evaluation runs retorna 409 (não 500/viola FK)."""
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]

    db_session.add(
        EvaluationRun(
            id=uuid.uuid4(),
            dataset_id=uuid.UUID(dataset_id),
            model="m",
            judge_type=JudgeType.DETERMINISTIC,
            status=RunStatus.DONE,
        )
    )
    await db_session.commit()

    response = await client.delete(f"/v1/datasets/{dataset_id}")
    assert response.status_code == 409

    # dataset continua existindo (nada foi apagado)
    detail = (await client.get(f"/v1/datasets/{dataset_id}")).json()
    assert detail["id"] == dataset_id


async def test_get_dataset_detail_with_samples_count(client: AsyncClient) -> None:
    """GET /v1/datasets/{id} retorna o dataset com contagem de samples real."""
    created = await client.post("/v1/datasets", json={"name": "ds-detalhe", "description": ""})
    dataset_id = created.json()["id"]

    await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[{"input": "q1", "expected_output": "a1"}],
    )

    response = await client.get(f"/v1/datasets/{dataset_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == dataset_id
    assert data["name"] == "ds-detalhe"
    assert data["samples_count"] == 1


async def test_list_samples_paginated(client: AsyncClient) -> None:
    """GET /v1/datasets/{id}/samples devolve samples paginados com total."""
    created = await client.post("/v1/datasets", json={"name": "ds-samples", "description": ""})
    dataset_id = created.json()["id"]

    await client.post(
        f"/v1/datasets/{dataset_id}/samples",
        json=[{"input": f"q{i}", "expected_output": f"a{i}"} for i in range(3)],
    )

    response = await client.get(f"/v1/datasets/{dataset_id}/samples", params={"limit": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert body["count"] == 2
    assert len(body["samples"]) == 2
    # Ordem é por created_at (a ordem exata da 1ª página é provada em
    # test_list_samples_orders_by_created_at); aqui checa os valores como conjunto.
    inputs = {s["input"] for s in body["samples"]}
    assert inputs <= {"q0", "q1", "q2"}
    assert all("expected_output" in s and isinstance(s["expected_output"], str) for s in body["samples"])


async def test_list_samples_orders_by_created_at(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Samples saem na ordem de created_at, não na ordem aleatória do id (uuid4)."""
    from datetime import UTC, datetime

    created = await client.post("/v1/datasets", json={"name": "ds-ord", "description": ""})
    dataset_id = created.json()["id"]
    ds_id = uuid.UUID(dataset_id)

    base = datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)
    # Insere FORA da ordem de created_at para provar que a ordenação usa created_at.
    plan = [("c", base.replace(microsecond=3)), ("a", base.replace(microsecond=1)),
            ("b", base.replace(microsecond=2))]
    for text, ts in plan:
        db_session.add(
            Sample(dataset_id=ds_id, input=text, expected_output="x", created_at=ts)
        )
    await db_session.commit()

    got = (await client.get(f"/v1/datasets/{dataset_id}/samples")).json()["samples"]
    assert [s["input"] for s in got] == ["a", "b", "c"]


async def test_list_samples_404_when_dataset_missing(client: AsyncClient) -> None:
    """Listar samples de dataset inexistente retorna 404."""
    response = await client.get(f"/v1/datasets/{uuid.uuid4()}/samples")
    assert response.status_code == 404


async def test_update_dataset_is_partial(client: AsyncClient) -> None:
    """PATCH /v1/datasets/{id} edita só os campos enviados e persiste."""
    created = await client.post("/v1/datasets", json={"name": "antes", "description": "d1"})
    dataset_id = created.json()["id"]

    resp = await client.patch(f"/v1/datasets/{dataset_id}", json={"name": "depois"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "depois"
    assert body["description"] == "d1"  # não enviado => inalterado
    assert body["samples_count"] == 0

    got = (await client.get(f"/v1/datasets/{dataset_id}")).json()
    assert got["name"] == "depois"
    assert got["description"] == "d1"


async def test_update_dataset_404_when_missing(client: AsyncClient) -> None:
    resp = await client.patch(f"/v1/datasets/{uuid.uuid4()}", json={"name": "x"})
    assert resp.status_code == 404


async def test_update_dataset_rejects_blank_name(client: AsyncClient) -> None:
    created = await client.post("/v1/datasets", json={"name": "ds", "description": ""})
    dataset_id = created.json()["id"]

    resp = await client.patch(f"/v1/datasets/{dataset_id}", json={"name": "   "})
    assert resp.status_code == 422


async def test_list_datasets_searches_by_name(client: AsyncClient) -> None:
    """`?q=` busca no nome (case-insensitive) — antes só dava para listar tudo."""
    await client.post("/v1/datasets", json={"name": "Alpha QA"})
    await client.post("/v1/datasets", json={"name": "Beta RAG"})

    resp = await client.get("/v1/datasets", params={"q": "alpha"})
    assert resp.status_code == 200, resp.text
    assert [d["name"] for d in resp.json()] == ["Alpha QA"]

    everything = (await client.get("/v1/datasets")).json()
    assert {d["name"] for d in everything} == {"Alpha QA", "Beta RAG"}
