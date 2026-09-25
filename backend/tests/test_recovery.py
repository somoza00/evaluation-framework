"""Testes do recovery de runs órfãs no startup (janela de idade)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.config import settings
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

    status_by_id = {
        run.id: run.status for run in (await db_session.execute(select(EvaluationRun))).scalars().all()
    }
    assert status_by_id[old.id] == RunStatus.FAILED
    assert status_by_id[recent.id] == RunStatus.RUNNING


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