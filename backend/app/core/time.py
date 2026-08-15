"""Helper de tempo compartilhado entre models e runner."""

from datetime import UTC, datetime


def utcnow_naive() -> datetime:
    """UTC "de verdade" sem tzinfo — datetime.utcnow() é deprecated e as
    colunas de datetime do banco são naive (sem timezone)."""
    return datetime.now(UTC).replace(tzinfo=None)
