"""Fixtures compartilhadas da suíte de testes."""

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Cliente HTTP async para testar os endpoints (usar ASGITransport)."""
    raise NotImplementedError
    yield  # pragma: no cover — mantém a assinatura como async generator


@pytest.fixture
async def db_session() -> AsyncGenerator[Any, None]:
    """Sessão async isolada contra o banco de teste (rollback por teste)."""
    raise NotImplementedError
    yield  # pragma: no cover — mantém a assinatura como async generator
