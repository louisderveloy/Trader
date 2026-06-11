"""change runs.optuna_study_id from integer to uuid

``optuna_studies.id`` is a UUID, but ``runs.optuna_study_id`` was an INTEGER, so
``RunManager.link_optuna_study()`` (which writes the study's UUID into that
column) always failed — the write is wrapped in a try/except and only logged, so
the link was silently never persisted. All existing values are NULL, so the
column is simply re-created with the correct type (mirrors the weights_set_id
fix in 7f964c375235).

Revision ID: 013
Revises: 012
Create Date: 2026-06-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All existing values are NULL, so drop and re-create as UUID (nullable).
    op.drop_column('runs', 'optuna_study_id')
    op.add_column(
        'runs',
        sa.Column('optuna_study_id', UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('runs', 'optuna_study_id')
    op.add_column(
        'runs',
        sa.Column('optuna_study_id', sa.Integer(), nullable=True),
    )
