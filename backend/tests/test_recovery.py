"""Testes do recovery de runs órfãs: janela de idade e sweep periódico.

O sweep do boot é uma passada só. Uma run que estava RUNNING quando o processo
caiu e cuja `created_at` é recente (menos de ORPHANED_RUN_MAX_AGE_SECONDS na
hora do restart) é poupada para não atrapalhar deploy rolling — e, sem uma
segunda passada, nunca mais era olhada: o worker só reivindica PENDING, então
ela ficava RUNNING para sempre na API/UI.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from typing import Self

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import main as app_main
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.time import utcnow_naive
from app.main import _recover_orphaned_runs
from app.models.evaluation import EvaluationRun, JudgeType, RunStatus


def _run(*, status: RunStatus, created_at) -> EvaluationRun:
    return EvaluationRun(
        dataset_id=uuid.uuid4(),
        model="gpt-4o",
        judge_type=JudgeType.LLM,
        status=status,
        created_at=created_at,
    )


async def test_recent_running_run_is_preserved_and_old_one_failed(db_session) -> None:
    """A janela de idade preserva runs RUNNING recém-criadas (deploy rolling)."""
    now = utcnow_naive()
    recent = _run(status=RunStatus.RUNNING, created_at=now)
    old = _run(
        status=RunStatus.RUNNING,
        created_at=now - timedelta(seconds=settings.ORPHANED_RUN_MAX_AGE_SECONDS + 60),
    )
    db_session.add_all([recent, old])
    await db_session.commit()

    await _recover_orphaned_runs(db_session)

    runs_by_id = {
        run.id: run for run in (await db_session.execute(select(EvaluationRun))).scalars().all()
    }
    assert runs_by_id[old.id].status == RunStatus.FAILED
    assert runs_by_id[recent.id].status == RunStatus.RUNNING
    # A órfã explica o que aconteceu; a run ainda ativa (deploy rolling) não
    # recebe motivo nenhum.
    assert runs_by_id[old.id].failure_reason is not None
    assert "interrompida" in (runs_by_id[old.id].failure_reason or "")
    assert runs_by_id[recent.id].failure_reason is None


async def test_done_and_failed_runs_are_left_untouched(db_session) -> None:
    """Recovery só toca em RUNNING; DONE/FAILED ficam como estão."""
    now = utcnow_naive()
    done = _run(status=RunStatus.DONE, created_at=now - timedelta(seconds=1000))
    failed = _run(status=RunStatus.FAILED, created_at=now - timedelta(seconds=1000))
    db_session.add_all([done, failed])
    await db_session.commit()

    await _recover_orphaned_runs(db_session)

    status_by_id = {
        run.id: run.status for run in (await db_session.execute(select(EvaluationRun))).scalars().all()
    }
    assert status_by_id[done.id] == RunStatus.DONE
    assert status_by_id[failed.id] == RunStatus.FAILED


async def test_orphaned_failed_run_gets_finished_at(db_session) -> None:
    """Uma run órfã marcada FAILED também ganha finished_at (antes ficava nulo)."""
    now = utcnow_naive()
    old = _run(
        status=RunStatus.RUNNING,
        created_at=now - timedelta(seconds=settings.ORPHANED_RUN_MAX_AGE_SECONDS + 60),
    )
    db_session.add(old)
    await db_session.commit()

    assert old.finished_at is None
    await _recover_orphaned_runs(db_session)

    # O bulk update não sincroniza o objeto já na identity map; popule do banco.
    recovered = await db_session.get(EvaluationRun, old.id, populate_existing=True)
    assert recovered.status == RunStatus.FAILED
    assert recovered.finished_at is not None


async def test_sweep_once_uses_its_own_session(
    db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A passada periódica abre sessão própria (não depende de request/sessão viva)."""
    engine = db_session.bind
    monkeypatch.setattr(app_main, "AsyncSessionLocal", lambda: AsyncSessionLocal(bind=engine))

    run = _run(
        status=RunStatus.RUNNING,
        created_at=utcnow_naive() - timedelta(seconds=settings.ORPHANED_RUN_MAX_AGE_SECONDS + 60),
    )
    db_session.add(run)
    await db_session.commit()

    await app_main.sweep_orphaned_runs_once()

    recovered = await db_session.get(EvaluationRun, run.id, populate_existing=True)
    assert recovered.status == RunStatus.FAILED


async def test_sweep_loop_repeats_and_survives_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """O loop repete a passada — e um erro de banco não mata o loop."""
    calls: list[int] = []

    async def _flaky_sweep() -> None:
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("blip do Postgres")

    monkeypatch.setattr(app_main, "sweep_orphaned_runs_once", _flaky_sweep)

    task = asyncio.create_task(app_main.orphan_sweep_loop(interval_seconds=0.01))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Uma exceção na primeira passada não impediu as seguintes.
    assert len(calls) >= 2


class _FakeSession:
    """Session context manager mínimo: o lifespan só abre e descarta."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def test_lifespan_starts_and_cancels_orphan_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    """O lifespan liga o sweep periódico e o cancela no shutdown."""
    started: list[str] = []
    cancelled: list[str] = []

    async def _fake_sweep() -> None:
        started.append("sweep")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append("sweep")
            raise

    async def _fake_worker() -> None:
        await asyncio.sleep(3600)

    async def _noop_recover(_session: AsyncSession) -> None:
        return None

    monkeypatch.setattr(app_main, "orphan_sweep_loop", _fake_sweep)
    monkeypatch.setattr(app_main, "run_worker_loop", _fake_worker)
    monkeypatch.setattr(app_main, "AsyncSessionLocal", _FakeSession)
    monkeypatch.setattr(app_main, "_recover_orphaned_runs", _noop_recover)
    # "production" pula o create_all (que exigiria um engine real).
    monkeypatch.setattr(app_main.settings, "APP_ENV", "production")

    async with app_main.lifespan(app_main.app):
        await asyncio.sleep(0)
        assert started == ["sweep"]

    assert cancelled == ["sweep"]
