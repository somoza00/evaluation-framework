"""failure_reason em evaluation_runs (diagnóstico de run FAILED)

Uma run que terminava em FAILED só tinha o status: dataset vazio, erro
estrutural no runner e processo morto no meio produziam o mesmo "failed" na
UI, e a causa ficava apenas no log do servidor. Coluna nullable (runs antigas
e runs DONE ficam com NULL).

Revision ID: b7c1e4d29a53
Revises: 7e530aeae969
Create Date: 2026-10-30 00:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c1e4d29a53"
down_revision: str | None = "7e530aeae969"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable sem server_default: linhas existentes ficam NULL (não há como
    # reconstruir a causa de uma run que já falhou) e o ADD COLUMN não reescreve
    # a tabela.
    op.add_column(
        "evaluation_runs",
        sa.Column("failure_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evaluation_runs", "failure_reason")
