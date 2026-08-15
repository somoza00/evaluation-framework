"""Endpoints de datasets: criação, upload de samples e listagem."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.dataset import Dataset, Sample

router = APIRouter(prefix="/datasets", tags=["datasets"])

# Sem limite, um POST /samples com lista gigante de textos grandes é DoS
# trivial por memória (tudo é bufferizado antes do bulk insert).
_MAX_SAMPLES_PER_REQUEST = 500
_MAX_FIELD_LENGTH = 20_000
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class DatasetCreate(BaseModel):
    """Body do POST /v1/datasets."""

    name: str = Field(max_length=255)
    description: str = Field(default="", max_length=5_000)


class SampleCreate(BaseModel):
    """Item do body (lista) do POST /v1/datasets/{id}/samples."""

    input: str = Field(max_length=_MAX_FIELD_LENGTH)
    expected_output: str = Field(max_length=_MAX_FIELD_LENGTH)
    metadata: dict[str, Any] = {}


class DatasetResponse(BaseModel):
    """Resposta de dataset (samples_count preenchido manualmente)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str
    created_at: datetime
    samples_count: int = 0


@router.post("", status_code=201, response_model=DatasetResponse)
async def create_dataset(
    payload: DatasetCreate,
    session: AsyncSession = Depends(get_session),
) -> DatasetResponse:
    """Cria um dataset (name, description) e retorna o registro criado."""
    dataset = Dataset(name=payload.name, description=payload.description)
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        created_at=dataset.created_at,
        samples_count=0,
    )


@router.post("/{dataset_id}/samples", status_code=201)
async def add_samples(
    dataset_id: uuid.UUID,
    payload: Annotated[list[SampleCreate], Body(max_length=_MAX_SAMPLES_PER_REQUEST)],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Cria múltiplos Samples em bulk; retorna count e ids criados."""
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset não encontrado")

    samples = [
        Sample(
            dataset_id=dataset_id,
            input=item.input,
            expected_output=item.expected_output,
            metadata_=item.metadata,
        )
        for item in payload
    ]
    session.add_all(samples)
    await session.commit()
    return {"count": len(samples), "ids": [sample.id for sample in samples]}


@router.get("", response_model=list[DatasetResponse])
async def list_datasets(
    limit: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = _DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_session),
) -> list[DatasetResponse]:
    """Lista datasets com contagem de samples (paginado: limit/offset)."""
    rows = (
        await session.execute(
            select(Dataset, func.count(Sample.id).label("samples_count"))
            .outerjoin(Sample, Sample.dataset_id == Dataset.id)
            .group_by(Dataset.id)
            .order_by(Dataset.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        DatasetResponse(
            id=dataset.id,
            name=dataset.name,
            description=dataset.description,
            created_at=dataset.created_at,
            samples_count=count,
        )
        for dataset, count in rows
    ]
