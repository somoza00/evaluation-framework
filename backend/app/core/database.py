"""Engine e sessão async do SQLAlchemy 2.0 + Base declarativa."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarativa usada por todos os models (e pelo Alembic)."""


engine: AsyncEngine = create_async_engine(settings.database_url)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency do FastAPI: entrega uma AsyncSession por request."""
    raise NotImplementedError
    yield  # pragma: no cover — mantém a assinatura como async generator
