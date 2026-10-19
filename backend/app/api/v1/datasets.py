"""Endpoints de datasets: criação, upload de samples e listagem."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.dataset import Dataset, Sample
from app.models.evaluation import EvaluationRun

router = APIRouter(prefix="/datasets", tags=["datasets"])

# Sem limite, um POST /samples com lista gigante de textos grandes é DoS
# trivial por memória (tudo é bufferizado antes do bulk insert).
_MAX_SAMPLES_PER_REQUEST = 500
_MAX_FIELD_LENGTH = 20_000
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class DatasetCreate(BaseModel):
    """Body do POST /v1/datasets."""

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=5_000)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        """Nome é o identificador exibível; rejeita vazio/só espaços (422)."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("name não pode ser vazio")
        return stripped


class DatasetUpdate(BaseModel):
    """Body do PATCH /v1/datasets/{id} — edição PARCIAL de name/description.

    Campos omitidos ficam inalterados (patch semântico); `name` em branco é
    rejeitado (422), como na criação.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5_000)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        """Nome é o identificador exibível; rejeita vazio/só espaços (422)."""
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name não pode ser vazio")
        return stripped


class SampleCreate(BaseModel):
    """Item do body (lista) do POST /v1/datasets/{id}/samples."""

    input: str = Field(max_length=_MAX_FIELD_LENGTH)
    expected_output: str = Field(max_length=_MAX_FIELD_LENGTH)
    metadata: dict[str, Any] = {}

    @field_validator("input", "expected_output")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Input/expected em branco degrada o judge p/ 0.0 silencioso; rejeita (422)."""
        if not value.strip():
            raise ValueError("input/expected_output não pode ser vazio")
        return value


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
    q: Annotated[
        str | None, Query(max_length=120, description="Busca por nome (case-insensitive).")
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> list[DatasetResponse]:
    """Lista datasets com contagem de samples (paginado: limit/offset).

    `q` (opcional) filtra pelo nome, case-insensitive e por substring — evita
    trazer a lista inteira para achar um dataset no seletor.
    """
    stmt = (
        select(Dataset, func.count(Sample.id).label("samples_count"))
        .outerjoin(Sample, Sample.dataset_id == Dataset.id)
        .group_by(Dataset.id)
        .order_by(Dataset.created_at.desc(), Dataset.id.desc())
    )
    if q is not None and q.strip():
        stmt = stmt.where(Dataset.name.ilike(f"%{q.strip()}%"))
    rows = (await session.execute(stmt.limit(limit).offset(offset))).all()
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


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> DatasetResponse:
    """Retorna um dataset com a contagem de samples; 404 se não existir."""
    row = (
        await session.execute(
            select(Dataset, func.count(Sample.id).label("samples_count"))
            .outerjoin(Sample, Sample.dataset_id == Dataset.id)
            .where(Dataset.id == dataset_id)
            .group_by(Dataset.id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="dataset não encontrado")
    dataset, count = row
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        created_at=dataset.created_at,
        samples_count=count,
    )


@router.get("/{dataset_id}/samples")
async def list_samples(
    dataset_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE_SIZE, description="Máx. de samples por página."),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Lista os samples de um dataset, paginado (limit/offset); 404 se dataset não existir."""
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset não encontrado")

    total = (
        await session.execute(
            select(func.count()).select_from(Sample).where(Sample.dataset_id == dataset_id)
        )
    ).scalar_one()

    samples = (
        await session.execute(
            select(Sample)
            .where(Sample.dataset_id == dataset_id)
            .order_by(Sample.created_at, Sample.id)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return {
        "dataset_id": str(dataset_id),
        "total": total,
        "limit": limit,
        "offset": offset,
        "count": len(samples),
        "samples": [
            {
                "id": str(sample.id),
                "input": sample.input,
                "expected_output": sample.expected_output,
                "metadata": sample.metadata_,
            }
            for sample in samples
        ],
    }


@router.patch("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: uuid.UUID,
    payload: DatasetUpdate,
    session: AsyncSession = Depends(get_session),
) -> DatasetResponse:
    """Edita name/description de um dataset (parcial); 404 se não existir.

    Devolve o dataset atualizado com o `samples_count`, para o cliente manter a
    lista coerente sem refazer um GET.
    """
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset não encontrado")
    if payload.name is not None:
        dataset.name = payload.name
    if payload.description is not None:
        dataset.description = payload.description
    await session.commit()
    await session.refresh(dataset)
    count = await session.scalar(
        select(func.count(Sample.id)).where(Sample.dataset_id == dataset_id)
    )
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        created_at=dataset.created_at,
        samples_count=count or 0,
    )


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    dataset_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Remove um dataset e seus samples (cascade manual — FK não tem CASCADE no banco).

    Apaga os samples antes do dataset, na mesma transação; 404 se não existir.
    """
    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="dataset não encontrado")
    # A FK evaluation_runs.dataset_id não tem ON DELETE CASCADE: apagar um
    # dataset com runs deixaria runs órfãs / violaria a FK no Postgres (500).
    runs_count = await session.scalar(
        select(func.count(EvaluationRun.id)).where(EvaluationRun.dataset_id == dataset_id)
    )
    if runs_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"dataset possui {runs_count} evaluation run(s); remova as runs antes",
        )
    await session.execute(delete(Sample).where(Sample.dataset_id == dataset_id))
    await session.delete(dataset)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
