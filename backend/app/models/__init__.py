"""Models — importar este pacote registra todas as tabelas no metadata.

Necessário para o Alembic (target_metadata) e para o metadata da Base.
"""

from app.core.database import Base
from app.models.dataset import Dataset, Sample
from app.models.evaluation import (
    EvaluationResult,
    EvaluationRun,
    JudgeType,
    RunStatus,
)
from app.models.judge import JudgeConfig

__all__ = [
    "Base",
    "Dataset",
    "EvaluationResult",
    "EvaluationRun",
    "JudgeConfig",
    "JudgeType",
    "RunStatus",
    "Sample",
]
