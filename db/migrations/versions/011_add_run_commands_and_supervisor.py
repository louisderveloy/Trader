"""add_run_commands_and_supervisor

Revision ID: 011
Revises: 010
Create Date: 2026-06-10 00:00:00.000000

Adds the run-control command channel used by the dashboard/API to start, stop
and kill runs via the RunSupervisor in the bot container:

- ``run_commands`` table: one row per command (start/stop/kill) with an atomic
  claim model (``processed_at``/``processed_by``) so a command is executed once.
- ``notify_run_command`` trigger: broadcasts new commands on the ``run_command``
  NOTIFY channel (mirrors the ``config_updated`` pattern in migration 008).
- ``runs.supervisor_pid``: lets the supervisor reconcile running children on restart.
- Partial unique indexes to defeat duplicate pending commands and to enforce the
  single-instance rule for paper/live runs at the database level.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create run_commands table, trigger, indexes and runs.supervisor_pid."""

    # ------------------------------------------------------------------
    # run_commands table — the control channel
    # ------------------------------------------------------------------
    op.create_table(
        'run_commands',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('run_id', sa.Integer(), nullable=False, comment='Target run'),
        sa.Column('kind', sa.String(10), nullable=False, comment='start, stop or kill'),
        sa.Column('params', JSONB, nullable=True, comment='Validated start params (start only)'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending',
                  comment='pending, processed, failed, expired'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('processed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('processed_by', sa.String(64), nullable=True, comment='Supervisor instance id that claimed it'),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_run_commands_run_id'),
        sa.CheckConstraint("kind IN ('start', 'stop', 'kill')", name='ck_run_commands_kind'),
        sa.CheckConstraint("status IN ('pending', 'processed', 'failed', 'expired')",
                           name='ck_run_commands_status'),
    )

    # Fast path for the supervisor poll fallback: only pending rows, oldest first.
    op.create_index(
        'idx_run_commands_pending', 'run_commands', ['created_at'],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Defeat duplicate pending commands of the same kind for the same run (Finding #5).
    op.create_index(
        'uq_run_commands_pending', 'run_commands', ['run_id', 'kind'], unique=True,
        postgresql_where=sa.text('processed_at IS NULL'),
    )

    # ------------------------------------------------------------------
    # NOTIFY trigger — mirrors notify_config_updated (migration 008)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_run_command()
        RETURNS trigger AS $$
        BEGIN
            PERFORM pg_notify(
                'run_command',
                json_build_object(
                    'id', NEW.id,
                    'kind', NEW.kind,
                    'run_id', NEW.run_id
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER on_run_command_inserted
        AFTER INSERT ON run_commands
        FOR EACH ROW
        EXECUTE FUNCTION notify_run_command();
    """)

    # ------------------------------------------------------------------
    # runs additions
    # ------------------------------------------------------------------
    op.add_column('runs', sa.Column('supervisor_pid', sa.Integer(), nullable=True,
                                    comment='OS PID of the spawned child, for supervisor restart reconciliation'))

    # Single-instance enforcement for paper/live at the DB level (Finding #15).
    # Backstops the bot's advisory locks against an API-layer race.
    op.execute("""
        CREATE UNIQUE INDEX uq_runs_single_instance
        ON runs (run_type)
        WHERE status IN ('pending', 'running') AND run_type IN ('paper', 'live')
    """)


def downgrade() -> None:
    """Drop everything created in upgrade()."""
    op.execute('DROP INDEX IF EXISTS uq_runs_single_instance')
    op.drop_column('runs', 'supervisor_pid')
    op.execute('DROP TRIGGER IF EXISTS on_run_command_inserted ON run_commands')
    op.execute('DROP FUNCTION IF EXISTS notify_run_command()')
    op.drop_table('run_commands')
