"""Configuração do judge LLM (Pydantic, não SQLAlchemy)."""

from pydantic import BaseModel


class JudgeConfig(BaseModel):
    """Parâmetros do judge LLM enviados ao gateway."""

    model: str
    temperature: float = 0.0
    max_tokens: int = 1024
    rubric: dict[str, str] = {}  # critério -> descrição
