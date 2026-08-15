"""Models SQLAlchemy de Dataset e Sample (tabelas ``datasets`` e ``samples``)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time import utcnow_naive


class Dataset(Base):
    """Agrupamento lógico de samples usado pelas evaluation runs."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)

    samples: Mapped[list["Sample"]] = relationship(back_populates="dataset")


class Sample(Base):
    """Par input/expected_output com metadata jsonb, pertencente a um dataset."""

    __tablename__ = "samples"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id"), nullable=False, index=True
    )
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    # Atributo metadata_ porque "metadata" é reservado pelo SQLAlchemy
    # (Base.metadata); a coluna no banco continua chamando "metadata".
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    dataset: Mapped["Dataset"] = relationship(back_populates="samples")
