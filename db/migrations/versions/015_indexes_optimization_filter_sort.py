"""indexes for optimization filtering and sorting

The Optimisations list view now filters (symbol, status, objective, active weights)
and sorts (completed_at, best_value) server-side. These partial/composite indexes on
the ``runs`` table back the common filter+sort access paths for ``run_type =
'optimization'`` rows so the dashboard list stays fast as history grows.

- ``ix_runs_opt_status_symbol``: filter by status and/or symbol within optimizations.
- ``ix_runs_opt_completed_at``: default sort (completed_at) within optimizations.

Both are partial indexes (``WHERE run_type = 'optimization'``) — small and targeted.
``best_value`` sorting reads ``optuna_studies`` joined on its existing ``run_id`` key.
Idempotent (IF NOT EXISTS); nothing is deleted.

Revision ID: 015
Revises: 014
Create Date: 2026-06-12

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_runs_opt_status_symbol
        ON runs (status, symbol)
        WHERE run_type = 'optimization'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_runs_opt_completed_at
        ON runs (completed_at DESC)
        WHERE run_type = 'optimization'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_runs_opt_completed_at")
    op.execute("DROP INDEX IF EXISTS ix_runs_opt_status_symbol")
