"""Testes de integração do EvaluationRunner: caminho feliz E2E e resiliência.

Antes desta suite, o runner só era exercitado via mock total (test_evaluations.py)
e o caminho PENDING -> RUNNING -> DONE nunca era percorrido de verdade.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset import Dataset, Sample
from app.models.evaluation import EvaluationResult, EvaluationRun, JudgeType, RunStatus
from app.services.runner import EvaluationRunner


def _fake_settings(**overrides: object) -> SimpleNamespace:
    """Settings mínimo só para o __init__ do runner (não usa banco)."""
    base: dict[str, object] = {
        "GATEWAY_URL": "http://gateway",
        "GATEWAY_API_KEY": "model-key",
        "JUDGE_API_KEY": None,
        "JUDGE_MODEL": "judge",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove o backoff real do retry para os testes rodarem instantâneos."""

    async def _noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.services.http_retry.asyncio.sleep", _noop)


async def _make_run(
    db_session: AsyncSession, judge_type: JudgeType, n_samples: int = 3
) -> EvaluationRun:
    dataset = Dataset(name="ds-runner")
    db_session.add(dataset)
    await db_session.flush()
    for i in range(n_samples):
        db_session.add(
            Sample(dataset_id=dataset.id, input=f"pergunta {i}", expected_output=f"resposta {i}")
        )
    run = EvaluationRun(dataset_id=dataset.id, model="m", judge_type=judge_type)
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def test_run_deterministic_end_to_end(db_session: AsyncSession) -> None:
    """POST /evaluations até DONE (com chamada real ao gateway mockado)."""
    run = await _make_run(db_session, JudgeType.DETERMINISTIC)

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "resposta 0"}}]})

    runner = EvaluationRunner(db_session, settings)
    runner.llm_judge.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )
    try:
        await runner.run(run.id)
    finally:
        await runner.close()

    await db_session.refresh(run)
    assert run.status == RunStatus.DONE
    assert run.finished_at is not None

    results = (
        await db_session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
    ).scalars().all()
    assert len(results) == 3
    assert all(r.score_overall is not None for r in results)


async def test_run_isolates_single_sample_failure(db_session: AsyncSession) -> None:
    """Erro ao chamar o modelo numa sample não derruba a run inteira (era FAILED total)."""
    run = await _make_run(db_session, JudgeType.DETERMINISTIC, n_samples=2)

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        if prompt == "pergunta 0":
            return httpx.Response(500)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    runner = EvaluationRunner(db_session, settings)
    runner.llm_judge.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )
    try:
        await runner.run(run.id)
    finally:
        await runner.close()

    await db_session.refresh(run)
    assert run.status == RunStatus.DONE  # não FAILED — a outra sample foi processada

    results = (
        await db_session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
    ).scalars().all()
    assert len(results) == 2
    failed = [r for r in results if r.actual_output == ""]
    ok = [r for r in results if r.actual_output == "ok"]
    assert len(failed) == 1
    assert "erro ao chamar o modelo avaliado" in (failed[0].judge_reasoning or "")
    assert len(ok) == 1


async def test_run_llm_judge_failure_records_none_score(db_session: AsyncSession) -> None:
    """Judge LLM fora do ar: resultado grava score_overall=None, run ainda DONE."""
    run = await _make_run(db_session, JudgeType.LLM, n_samples=1)

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if len(body["messages"]) == 1:
            # chamada ao modelo avaliado: sucesso
            return httpx.Response(200, json={"choices": [{"message": {"content": "resposta"}}]})
        # chamada ao judge (system + user): gateway fora do ar
        return httpx.Response(500)

    runner = EvaluationRunner(db_session, settings)
    runner.llm_judge.client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    )
    try:
        await runner.run(run.id)
    finally:
        await runner.close()

    await db_session.refresh(run)
    assert run.status == RunStatus.DONE

    results = (
        await db_session.execute(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
    ).scalars().all()
    assert len(results) == 1
    assert results[0].score_overall is None
    assert "erro ao avaliar via LLM" in (results[0].judge_reasoning or "")


async def test_judge_uses_separate_key_when_configured() -> None:
    """Com JUDGE_API_KEY definida, o judge usa a própria chave (não a do modelo)."""
    runner = EvaluationRunner(
        session=AsyncMock(), settings=_fake_settings(JUDGE_API_KEY="judge-key")  # type: ignore[arg-type]
    )
    try:
        assert runner.llm_judge.api_key == "judge-key"
    finally:
        await runner.close()


async def test_judge_falls_back_to_model_key_when_unset() -> None:
    """Sem JUDGE_API_KEY, o judge usa a mesma de GATEWAY_API_KEY (retrocompat)."""
    runner = EvaluationRunner(
        session=AsyncMock(), settings=_fake_settings(JUDGE_API_KEY=None)  # type: ignore[arg-type]
    )
    try:
        assert runner.llm_judge.api_key == "model-key"
    finally:
        await runner.close()
