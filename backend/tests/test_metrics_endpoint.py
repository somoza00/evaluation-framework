"""Testes do /metrics (Prometheus) e dos contadores incrementados pelo runner."""

from __future__ import annotations

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset import Dataset, Sample
from app.models.evaluation import EvaluationResult, EvaluationRun, JudgeType, RunStatus
from app.services import metrics
from app.services.runner import EvaluationRunner


def _counter_value(counter: object) -> float:
    """Lê o valor atual de um `Counter` filho (ex.: `.labels(status="done")`)."""
    return counter._value.get()  # type: ignore[attr-defined]


async def test_metrics_endpoint_exposes_runner_series(client: AsyncClient) -> None:
    """`GET /metrics` responde no formato de scrape e traz as séries do runner."""
    resp = await client.get("/metrics")

    assert resp.status_code == 200, resp.text
    assert "text/plain" in resp.headers["content-type"]
    # A série existe mesmo antes de qualquer run (valor 0): o Prometheus precisa
    # do nome para descobrir o alvo, não só do dado.
    assert "eval_runs_finished_total" in resp.text
    assert "eval_results_persisted_total" in resp.text
    assert "eval_run_duration_seconds" in resp.text


async def test_metrics_endpoint_nao_exige_api_key(client: AsyncClient) -> None:
    """Scraper de infra não manda X-API-Key: `/metrics` é aberto, como `/health`."""
    assert (await client.get("/metrics", headers={"X-API-Key": "errada"})).status_code == 200
    assert (await client.get("/metrics")).status_code == 200


async def test_record_run_finished_incrementa_status_e_observa_duracao() -> None:
    before_done = _counter_value(metrics.RUNS_FINISHED.labels(status="done"))
    before_failed = _counter_value(metrics.RUNS_FINISHED.labels(status="failed"))

    metrics.record_run_finished(status="done", duration_seconds=1.5)
    metrics.record_run_finished(status="failed", duration_seconds=-3.0)  # clamp em 0

    assert _counter_value(metrics.RUNS_FINISHED.labels(status="done")) == before_done + 1
    assert _counter_value(metrics.RUNS_FINISHED.labels(status="failed")) == before_failed + 1


async def test_record_result_incrementa_por_desfecho() -> None:
    before = _counter_value(metrics.RESULTS_PERSISTED.labels(outcome="scored"))

    metrics.record_result(outcome="scored")
    metrics.record_result(outcome="scored")

    assert _counter_value(metrics.RESULTS_PERSISTED.labels(outcome="scored")) == before + 2


async def _make_run(db_session: AsyncSession, n_samples: int) -> EvaluationRun:
    dataset = Dataset(name="ds-metrics")
    db_session.add(dataset)
    await db_session.flush()
    for i in range(n_samples):
        db_session.add(
            Sample(dataset_id=dataset.id, input=f"pergunta {i}", expected_output=f"resposta {i}")
        )
    run = EvaluationRun(dataset_id=dataset.id, model="m", judge_type=JudgeType.DETERMINISTIC)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


@pytest.mark.parametrize(("n_samples", "status_esperado"), [(2, "done"), (0, "failed")])
async def test_runner_conta_run_finalizada_e_resultados(
    db_session: AsyncSession, n_samples: int, status_esperado: str
) -> None:
    """O contador de runs finalizadas e o de resultados acompanham o runner de verdade."""
    run = await _make_run(db_session, n_samples)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "resposta 0"}}]})

    runner = EvaluationRunner(db_session, settings)
    runner.llm_judge.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )
    before_runs = _counter_value(metrics.RUNS_FINISHED.labels(status=status_esperado))
    before_scored = _counter_value(metrics.RESULTS_PERSISTED.labels(outcome="scored"))
    try:
        await runner.run(run.id)
    finally:
        await runner.close()

    await db_session.refresh(run)
    assert run.status == (RunStatus.DONE if n_samples else RunStatus.FAILED)
    assert _counter_value(metrics.RUNS_FINISHED.labels(status=status_esperado)) == before_runs + 1
    # Um resultado persistido por sample avaliada (judge determinístico sempre dá nota).
    assert _counter_value(metrics.RESULTS_PERSISTED.labels(outcome="scored")) == (
        before_scored + n_samples
    )

    results = (
        await db_session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
    ).scalars().all()
    assert len(results) == n_samples
