"""Endpoints de resultados: consulta por run e comparação entre runs."""

from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/results", tags=["results"])


# Ordem importa: /compare é rota estática e precisa vir antes de /{run_id}.
@router.get("/compare")
async def compare_results(
    runs: str = Query(..., description="IDs de runs separados por vírgula (ex: 1,2,3)"),
) -> dict[str, Any]:
    """Compara métricas agregadas entre múltiplas runs."""
    raise NotImplementedError


@router.get("/{run_id}")
async def get_results(run_id: int) -> dict[str, Any]:
    """Retorna todos os EvaluationResult de uma run."""
    raise NotImplementedError
