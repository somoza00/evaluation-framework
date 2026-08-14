"""Models SQLAlchemy de EvaluationRun e EvaluationResult."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.judge import JudgeType, RunStatus


class EvaluationRun(Base):
    """Execução de uma avaliação: dataset + model + judge(s) + status."""

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    model: Mapped[str] = mapped_column(String(255))
    judge_type: Mapped[JudgeType] = mapped_column(
        Enum(JudgeType, name="judge_type"), default=JudgeType.LLM
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status"), default=RunStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    results: Mapped[list["EvaluationResult"]] = relationship(back_populates="run")


class EvaluationResult(Base):
    """Score por sample dentro de uma run (fidelity, coherence, instruction, overall)."""

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id", ondelete="CASCADE"))
    actual_output: Mapped[str] = mapped_column(Text)
    score_fidelity: Mapped[float | None] = mapped_column(Float)
    score_coherence: Mapped[float | None] = mapped_column(Float)
    score_instruction: Mapped[float | None] = mapped_column(Float)
    score_overall: Mapped[float | None] = mapped_column(Float)
    judge_reasoning: Mapped[str | None] = mapped_column(Text)
    # Coluna "metadata" no banco; atributo metadata_ (ver dataset.py).
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
