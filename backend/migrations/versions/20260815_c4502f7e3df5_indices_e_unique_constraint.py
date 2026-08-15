"""indices em FKs + unique constraint (run_id, sample_id)

Sem índices, as queries de listar/comparar/calcular progresso (que filtram
por dataset_id/run_id/sample_id) varreriam a tabela toda conforme os dados
crescem. Sem a unique constraint, um retry de gravação de resultado (ex:
reprocessar uma sample) duplicava a linha em vez de falhar de forma óbvia.

Revision ID: c4502f7e3df5
Revises: a2c937bccfa6
Create Date: 2026-08-15 00:00:00.000000+00:00

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4502f7e3df5'
down_revision: str | None = 'a2c937bccfa6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f('ix_samples_dataset_id'), 'samples', ['dataset_id'], unique=False
    )
    op.create_index(
        op.f('ix_evaluation_runs_dataset_id'), 'evaluation_runs', ['dataset_id'], unique=False
    )
    op.create_index(
        op.f('ix_evaluation_results_run_id'), 'evaluation_results', ['run_id'], unique=False
    )
    op.create_index(
        op.f('ix_evaluation_results_sample_id'), 'evaluation_results', ['sample_id'], unique=False
    )
    op.create_unique_constraint(
        'uq_evaluation_results_run_sample', 'evaluation_results', ['run_id', 'sample_id']
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_evaluation_results_run_sample', 'evaluation_results', type_='unique'
    )
    op.drop_index(op.f('ix_evaluation_results_sample_id'), table_name='evaluation_results')
    op.drop_index(op.f('ix_evaluation_results_run_id'), table_name='evaluation_results')
    op.drop_index(op.f('ix_evaluation_runs_dataset_id'), table_name='evaluation_runs')
    op.drop_index(op.f('ix_samples_dataset_id'), table_name='samples')
