"""created_at em samples e evaluation_results (ordem de listagem)

A listagem de samples e a consulta de resultados ordenavam por `id`, que é uuid4
(aleatório) — a ordem saía embaralhada, impossível de correlacionar com a linha
do CSV enviado. Adiciona `created_at` para preservar a ordem de inserção.

Revision ID: 7e530aeae969
Revises: c4502f7e3df5
Create Date: 2026-10-11 00:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7e530aeae969"
down_revision: str | None = "c4502f7e3df5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # As tabelas já têm linhas em produção: adicionar uma coluna NOT NULL exige
    # um server_default (o `now()` preenche as linhas existentes no ADD COLUMN).
    for table in ("samples", "evaluation_results"):
        op.add_column(
            table,
            sa.Column(
                "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
            ),
        )


def downgrade() -> None:
    for table in ("evaluation_results", "samples"):
        op.drop_column(table, "created_at")
