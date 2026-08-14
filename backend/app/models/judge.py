"""Enums compartilhados do fluxo de avaliação (judge e status da run)."""

from enum import Enum


class JudgeType(str, Enum):
    """Tipo de judge usado em uma evaluation run."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    BOTH = "both"


class RunStatus(str, Enum):
    """Ciclo de vida de uma evaluation run."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
