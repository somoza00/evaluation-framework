"""Testes da normalização de DATABASE_URL para providers gerenciados (Neon)."""

from app.core.database import build_engine_kwargs


def test_sqlite_url_is_untouched() -> None:
    """URL de teste (sqlite in-memory) não deve ganhar connect_args de SSL."""
    url, connect_args = build_engine_kwargs("sqlite+aiosqlite://")
    assert url == "sqlite+aiosqlite://"
    assert connect_args == {}


def test_local_compose_postgres_is_untouched() -> None:
    """Postgres local (db:5432 do docker-compose) não precisa de SSL."""
    url, connect_args = build_engine_kwargs(
        "postgresql+asyncpg://eval:eval@db:5432/evaluation"
    )
    assert url == "postgresql+asyncpg://eval:eval@db:5432/evaluation"
    assert connect_args == {}


def test_remote_postgres_gets_ssl_and_drops_sslmode() -> None:
    """Host remoto (ex: Neon) ganha ssl=True e perde o sslmode= incompatível."""
    url, connect_args = build_engine_kwargs(
        "postgresql+asyncpg://user:pw@ep-xyz.aws.neon.tech/evaluation?sslmode=require"
    )
    assert "sslmode" not in url
    assert url.startswith("postgresql+asyncpg://user:pw@ep-xyz.aws.neon.tech/evaluation")
    assert connect_args == {"ssl": True}
