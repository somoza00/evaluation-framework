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
