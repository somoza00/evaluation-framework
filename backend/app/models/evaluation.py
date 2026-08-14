"""Models SQLAlchemy de EvaluationRun/EvaluationResult + enums do fluxo."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JudgeType(str, enum.Enum):
    """Tipo de judge usado em uma evaluation run."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    BOTH = "both"


class RunStatus(str, enum.Enum):
    """Ciclo de vida de uma evaluation run."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class EvaluationRun(Base):
    """Execução de uma avaliação: dataset + model + judge(s) + status."""

    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    judge_type: Mapped[JudgeType] = mapped_column(
        SQLAlchemyEnum(JudgeType), nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(
        SQLAlchemyEnum(RunStatus), default=RunStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    results: Mapped[list["EvaluationResult"]] = relationship(back_populates="run")


class EvaluationResult(Base):
    """Score por sample dentro de uma run (fidelity, coherence, instruction, overall)."""

    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id"), nullable=False
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("samples.id"), nullable=False
    )
    actual_output: Mapped[str] = mapped_column(Text, nullable=False)
    # Mapped[float | None] sem mapped_column: coluna Float nullable inferida.
    score_fidelity: Mapped[float | None]
    score_coherence: Mapped[float | None]
    score_instruction: Mapped[float | None]
    score_overall: Mapped[float | None]
    judge_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Coluna "metadata" no banco; atributo metadata_ (ver dataset.py).
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    run: Mapped["EvaluationRun"] = relationship(back_populates="results")
