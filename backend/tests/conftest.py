"""Fixtures compartilhadas: banco SQLite in-memory async + cliente HTTP."""

from collections.abc import AsyncGenerator, Iterator

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


@pytest.fixture(autouse=True)
def _reset_rate_limit_hits() -> Iterator[None]:
    """Zera o contador do rate-limit em memória antes e depois de cada teste.

    O limiter é estado de MÓDULO (`security._hits`) com janela de 60s: todos os
    testes usam o mesmo IP (`testclient`), então a suíte inteira consumia o mesmo
    balde de 120 req/min. Ao somar ~120 requests, os testes que rodavam por
    último começavam a receber 429 de um limite que não têm nada a ver com o que
    estão verificando (a falha aparecia em test_results.py, longe da causa) — e
    qualquer teste novo podia derrubar a suíte por "excesso de tráfego". Os
    testes do próprio limite (test_security.py) continuam válidos: eles contam
    requests DENTRO de um teste, e o balde começa vazio em cada um.
    """
    from app.core.security import _hits

    _hits.clear()
    yield
    _hits.clear()


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
