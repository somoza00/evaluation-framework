"""Endpoints de resultados: consulta por run, comparação entre runs e export CSV."""

import csv
import io
import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.dataset import Sample
from app.models.evaluation import EvaluationResult, EvaluationRun

router = APIRouter(prefix="/results", tags=["results"])

_SCORE_FIELDS = ("score_fidelity", "score_coherence", "score_instruction", "score_overall")

# Colunas do CSV exportado (ordem fixa = cabeçalho da planilha).
_CSV_COLUMNS = (
    "sample_id",
    "input",
    "expected_output",
    "actual_output",
    "score_overall",
    "score_fidelity",
    "score_coherence",
    "score_instruction",
    "judge_reasoning",
)


class ResultResponse(BaseModel):
    """Resposta de um EvaluationResult."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sample_id: uuid.UUID
    actual_output: str
    score_fidelity: float | None
    score_coherence: float | None
    score_instruction: float | None
    score_overall: float | None
    judge_reasoning: str | None
    # Preenchidos por join com `samples` — o frontend (ResultsTable) exibe o
    # input/esperado de cada sample na tabela; sem isto a tabela mostrava "—".
    input: str | None = None
    expected_output: str | None = None


def _averages(results: Sequence[EvaluationResult]) -> dict[str, float | None]:
    """Média de cada score sobre os valores não-None (None se vazio)."""
    averages: dict[str, float | None] = {}
    for field in _SCORE_FIELDS:
        values = [getattr(result, field) for result in results if getattr(result, field) is not None]
        averages[field] = sum(values) / len(values) if values else None
    return averages


# Ordem importa: /compare é rota estática e precisa vir antes de /{run_id}.
@router.get("/compare")
async def compare_results(
    runs: str = Query(..., description="IDs de runs separados por vírgula (ex: 1,2,3)"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Compara médias de score entre múltiplas runs (side-by-side)."""
    try:
        seen: set[uuid.UUID] = set()
        run_ids: list[uuid.UUID] = []
        for part in runs.split(","):
            part = part.strip()
            if not part:
                continue
            uid = uuid.UUID(part)
            if uid not in seen:
                seen.add(uid)
                run_ids.append(uid)
    except ValueError:
        raise HTTPException(status_code=422, detail="runs deve conter UUIDs separados por vírgula")
    if not run_ids:
        raise HTTPException(status_code=422, detail="informe ao menos um run_id")

    runs_found = (
        await session.execute(select(EvaluationRun).where(EvaluationRun.id.in_(run_ids)))
    ).scalars().all()
    if len(runs_found) != len(run_ids):
        raise HTTPException(status_code=404, detail="uma ou mais runs não encontradas")

    # Respeita a ordem pedida pelo client (runs=B,A,C => resposta [B,A,C]),
    # em vez da ordem do banco (por inserção), para o side-by-side não desalinhar.
    runs_by_id = {run.id: run for run in runs_found}
    comparison = []
    for run in (runs_by_id[run_id] for run_id in run_ids):
        results = (
            await session.execute(
                select(EvaluationResult).where(EvaluationResult.run_id == run.id)
            )
        ).scalars().all()
        comparison.append(
            {
                "run_id": str(run.id),
                "model": run.model,
                "judge_type": run.judge_type.value,
                "status": run.status.value,
                "averages": _averages(results),
            }
        )
    return {"runs": comparison}


_MAX_PAGE_SIZE = 200


def _csv_value(result: EvaluationResult, sample: Sample | None, column: str) -> str:
    """Valor de uma célula do export, com None como célula vazia e score com 4 casas."""
    if column in ("input", "expected_output"):
        return (getattr(sample, column) if sample is not None else None) or ""
    if column in _SCORE_FIELDS:
        value = getattr(result, column)
        return "" if value is None else f"{value:.4f}"
    if column == "sample_id":
        return str(result.sample_id)
    if column == "judge_reasoning":
        return result.judge_reasoning or ""
    return str(getattr(result, column))


@router.get("/{run_id}/export")
async def export_results_csv(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Exporta TODOS os resultados de uma run como CSV (download para planilha).

    O frontend só mostra tabela paginada; para analisar uma run inteira (ou
    mandar para alguém) não havia caminho sem script. O arquivo traz, por
    sample: input, saída esperada, saída real, os quatro scores e o reasoning do
    juiz. Score ausente (falha do judge) fica como célula vazia — não como 0,
    que viraria nota legítima na média da planilha.

    Não é paginado de propósito: o CSV é o artefato completo da run (500 samples
    x ~40KB no pior caso continuam sendo alguns MB, servidos numa resposta só).
    """
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run não encontrada")

    results = (
        await session.execute(
            select(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
            .order_by(EvaluationResult.created_at, EvaluationResult.id)
        )
    ).scalars().all()

    samples_by_id: dict[uuid.UUID, Sample] = {}
    if results:
        samples = (
            await session.execute(
                select(Sample).where(Sample.id.in_([r.sample_id for r in results]))
            )
        ).scalars().all()
        samples_by_id = {sample.id: sample for sample in samples}

    buffer = io.StringIO()
    # `\r\n` (default do csv) é o que Excel/Sheets esperam; o reader dos testes
    # entende os dois.
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(_CSV_COLUMNS)
    for result in results:
        sample = samples_by_id.get(result.sample_id)
        writer.writerow([_csv_value(result, sample, column) for column in _CSV_COLUMNS])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="run-{run_id}.csv"',
            # O conteúdo depende do banco; proxy/CDN não deve servir um CSV velho.
            "Cache-Control": "no-store",
        },
    )


@router.get("/{run_id}")
async def get_results(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE_SIZE, description="Máx. de resultados por página."),
    offset: int = Query(default=0, ge=0, description="Pula resultados no início."),
) -> dict[str, Any]:
    """Retorna EvaluationResults de uma run, paginado (limit/offset), com médias dos scores."""
    run = await session.get(EvaluationRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run não encontrada")

    total = (
        await session.execute(
            select(func.count())
            .select_from(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
        )
    ).scalar_one()

    results = (
        await session.execute(
            select(EvaluationResult)
            .where(EvaluationResult.run_id == run_id)
            .order_by(EvaluationResult.created_at, EvaluationResult.id)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    # Médias sobre TODOS os resultados da run (não só a página): senão páginas
    # diferentes mostram médias diferentes e divergem de /compare.
    all_results = (
        await session.execute(
            select(EvaluationResult).where(EvaluationResult.run_id == run_id)
        )
    ).scalars().all()

    # Join com os samples para expor input/expected_output de cada resultado
    # (a página de Results mostra isso na tabela).
    sample_ids = [result.sample_id for result in results]
    samples_by_id: dict[uuid.UUID, Sample] = {}
    if sample_ids:
        samples = (
            await session.execute(select(Sample).where(Sample.id.in_(sample_ids)))
        ).scalars().all()
        samples_by_id = {sample.id: sample for sample in samples}

    payload = []
    for result in results:
        sample = samples_by_id.get(result.sample_id)
        item = ResultResponse.model_validate(result).model_dump()
        item["input"] = sample.input if sample is not None else None
        item["expected_output"] = sample.expected_output if sample is not None else None
        payload.append(item)
    return {
        "run_id": str(run_id),
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(results),
        "averages": _averages(all_results),
        "results": payload,
    }
