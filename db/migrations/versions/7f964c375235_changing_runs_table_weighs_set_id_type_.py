"""changing runs table weighs_set_id type from interger to uuid

Revision ID: 7f964c375235
Revises: 003
Create Date: 2026-06-05 22:33:56.313321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '7f964c375235'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    # Step 1: drop the existing integer column
    op.drop_column('runs', 'weights_set_id')

    # Step 2: re-create it as UUID, nullable to avoid constraint issues on existing rows
    op.add_column(
        'runs',
        sa.Column(
            'weights_set_id',
            UUID(as_uuid=True),
            nullable=True
        )
    )


def downgrade() -> None:
    # Step 1: drop the UUID column
    op.drop_column('runs', 'weights_set_id')

    # Step 2: re-create it as INTEGER (nullable to match the rollback safely)
    op.add_column(
        'runs',
        sa.Column(
            'weights_set_id',
            sa.Integer(),
            nullable=True
        )
    )