"""Fixtures compartilhadas: banco SQLite in-memory async + cliente HTTP."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from app.core.database import AsyncSessionLocal, Base, get_session
from app.main import app


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: JSONB, compiler: object, **kw: object) -> str:
    """SQLite não tem JSONB nativo: compila como JSON (TEXT) nos testes."""
    return "JSON"


# SQLite in-memory é por conexão: sem StaticPool, cada conexão enxergaria um
# banco vazio (create_all numa, requests em outra). Conexão única compartilhada.
_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """SQLite in-memory async session para testes (schema recriado por teste)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal(bind=_engine) as session:
        yield session
    await _engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient com override de get_session para a sessão de teste."""
    app.dependency_overrides[get_session] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
