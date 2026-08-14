"""Engine e sessão async do SQLAlchemy 2.0 + Base declarativa."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarativa usada por todos os models (e pelo Alembic)."""


engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency do FastAPI: entrega uma AsyncSession por request."""
    async with AsyncSessionLocal() as session:
        yield session
