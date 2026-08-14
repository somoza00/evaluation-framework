"""Models SQLAlchemy de Dataset e Sample (tabelas ``datasets`` e ``samples``)."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Dataset(Base):
    """Agrupamento lógico de samples usado pelas evaluation runs."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    samples: Mapped[list["Sample"]] = relationship(back_populates="dataset")


class Sample(Base):
    """Par input/expected_output com metadata jsonb, pertencente a um dataset."""

    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    input: Mapped[str] = mapped_column(Text)
    expected_output: Mapped[str] = mapped_column(Text)
    # Atributo metadata_ porque "metadata" é reservado pelo SQLAlchemy
    # (Base.metadata); a coluna no banco continua chamando "metadata".
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    dataset: Mapped[Dataset] = relationship(back_populates="samples")
