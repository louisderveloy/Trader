"""backfill runs.weights_set_id from optuna_studies

When an optimization completes, the runner saves the produced weights set on the
``optuna_studies`` row (``optuna_studies.weights_set_id``) and links the study to
the run, but it never wrote ``runs.weights_set_id`` — so that column was NULL for
every completed optimization run. The runner now records it (via
``RunManager.link_optuna_study(..., weights_set_id=...)``); this migration backfills
the existing rows so the dashboard can find each run's weights set directly.

Data-only, idempotent (only fills rows still NULL). Nothing is deleted.

Revision ID: 014
Revises: 013
Create Date: 2026-06-11

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '014'
down_revision: Union[str, None] = '013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Copy the weights set produced by each study onto its run. Pick the most
    # recent study per run in case a run was (re)linked more than once.
    op.execute(
        """
        UPDATE runs r
        SET weights_set_id = s.weights_set_id
        FROM (
            SELECT DISTINCT ON (run_id) run_id, weights_set_id
            FROM optuna_studies
            WHERE run_id IS NOT NULL AND weights_set_id IS NOT NULL
            ORDER BY run_id, created_at DESC
        ) s
        WHERE r.id = s.run_id
          AND r.weights_set_id IS NULL
        """
    )


def downgrade() -> None:
    # No-op: backfilled values are indistinguishable from values written live by
    # the runner, so we do not clear them on downgrade.
    pass
