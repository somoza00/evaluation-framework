"""Endpoints de datasets: criação, upload de samples e listagem."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.dataset import Dataset, Sample

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetCreate(BaseModel):
    """Body do POST /v1/datasets."""

    name: str
    description: str = ""


class SampleCreate(BaseModel):
    """Item do body (lista) do POST /v1/datasets/{id}/samples."""

    input: str
    expected_output: str
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
    payload: list[SampleCreate],
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
    session: AsyncSession = Depends(get_session),
) -> list[DatasetResponse]:
    """Lista todos os datasets com contagem de samples."""
    rows = (
        await session.execute(
            select(Dataset, func.count(Sample.id).label("samples_count"))
            .outerjoin(Sample, Sample.dataset_id == Dataset.id)
            .group_by(Dataset.id)
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
