"""Models SQLAlchemy — importar este pacote registra todas as tabelas.

Necessário para o Alembic (target_metadata) e para o metadata da Base.
"""

from app.core.database import Base
from app.models.dataset import Dataset, Sample
from app.models.evaluation import EvaluationResult, EvaluationRun
from app.models.judge import JudgeType, RunStatus

__all__ = [
    "Base",
    "Dataset",
    "EvaluationResult",
    "EvaluationRun",
    "JudgeType",
    "RunStatus",
    "Sample",
]
