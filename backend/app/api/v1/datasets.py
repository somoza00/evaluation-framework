"""Endpoints de datasets: criação, upload de samples e listagem."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("")
async def create_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    """Cria um dataset (name, description) e retorna o registro criado."""
    raise NotImplementedError


@router.post("/{dataset_id}/samples")
async def add_samples(dataset_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Adiciona samples a um dataset (lista de {input, expected_output, metadata})."""
    raise NotImplementedError


@router.get("")
async def list_datasets() -> list[dict[str, Any]]:
    """Lista todos os datasets."""
    raise NotImplementedError
