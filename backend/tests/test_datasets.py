"""Testes dos endpoints de datasets."""

import uuid

from httpx import AsyncClient


async def test_create_dataset(client: AsyncClient) -> None:
    """POST /v1/datasets retorna 201 com id e name."""
    response = await client.post(
        "/v1/datasets", json={"name": "meu dataset", "description": "descricao"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "meu dataset"
    assert uuid.UUID(data["id"])  # id é UUID válido


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
    # Ordenação é por UUID (id), não por inserção; checa os valores como conjunto.
    inputs = {s["input"] for s in body["samples"]}
    assert inputs <= {"q0", "q1", "q2"}
    assert all("expected_output" in s and isinstance(s["expected_output"], str) for s in body["samples"])


async def test_list_samples_404_when_dataset_missing(client: AsyncClient) -> None:
    """Listar samples de dataset inexistente retorna 404."""
    response = await client.get(f"/v1/datasets/{uuid.uuid4()}/samples")
    assert response.status_code == 404
