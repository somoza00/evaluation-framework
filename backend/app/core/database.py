"""Engine e sessão async do SQLAlchemy 2.0 + Base declarativa."""

from collections.abc import AsyncGenerator

from sqlalchemy import make_url
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarativa usada por todos os models (e pelo Alembic)."""


_LOCAL_HOSTS = {None, "", "localhost", "127.0.0.1", "db"}


def build_engine_kwargs(database_url: str) -> tuple[str, dict[str, object]]:
    """Normaliza a DATABASE_URL e decide os connect_args de SSL.

    Provedores gerenciados (ex: Neon) exigem TLS e costumam enviar a URL
    com `?sslmode=require` — sintaxe do psycopg/libpq que o driver asyncpg
    não entende (ele quebra com um `TypeError` na conexão). Aqui removemos
    esse parâmetro da URL e, se o host não for local (sqlite de teste ou
    Postgres do docker-compose), passamos `ssl=True` via connect_args, que é
    o formato que o asyncpg espera.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or url.host in _LOCAL_HOSTS:
        return database_url, {}

    query = dict(url.query)
    query.pop("sslmode", None)
    clean_url: URL = url.set(query=query)
    return clean_url.render_as_string(hide_password=False), {"ssl": True}


_url, _connect_args = build_engine_kwargs(settings.DATABASE_URL)
engine = create_async_engine(_url, echo=False, connect_args=_connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency do FastAPI: entrega uma AsyncSession por request."""
    async with AsyncSessionLocal() as session:
        yield session
