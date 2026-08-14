"""Endpoints de avaliações: criação, listagem e detalhe de runs."""

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("")
async def create_evaluation(payload: dict[str, Any]) -> dict[str, Any]:
    """Cria uma run (dataset_id, model, judge_type) e dispara a avaliação."""
    raise NotImplementedError


@router.get("")
async def list_evaluations() -> list[dict[str, Any]]:
    """Lista todas as evaluation runs com status."""
    raise NotImplementedError


@router.get("/{evaluation_id}")
async def get_evaluation(evaluation_id: int) -> dict[str, Any]:
    """Retorna detalhes de uma run (inclui resultados agregados)."""
    raise NotImplementedError
