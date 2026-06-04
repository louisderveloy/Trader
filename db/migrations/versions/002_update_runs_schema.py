"""update_runs_schema

Revision ID: 002
Revises: 001
Create Date: 2026-06-04 22:30:00.000000

Updates runs table to match bot code expectations:
- Add environment column
- Add symbol, timeframe, start_date, end_date columns
- Add result JSONB column
- Add weights_set_id, optuna_study_id columns
- Change id from UUID to SERIAL
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop foreign key constraints temporarily
    op.drop_constraint('fk_indicators_values_run_id', 'indicators_values', type_='foreignkey')
    op.drop_constraint('fk_signals_run_id', 'signals', type_='foreignkey')
    op.drop_constraint('fk_orders_run_id', 'orders', type_='foreignkey')
    op.drop_constraint('fk_trades_run_id', 'trades', type_='foreignkey')
    op.drop_constraint('fk_errors_log_run_id', 'errors_log', type_='foreignkey')
    op.drop_constraint('fk_optuna_studies_run_id', 'optuna_studies', type_='foreignkey')

    # Drop existing runs table and recreate with new schema
    op.drop_table('runs')

    # Create new runs table with INTEGER id
    op.create_table(
        'runs',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('run_type', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('environment', sa.String(20), nullable=False, server_default='dev'),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('timeframe', sa.String(10), nullable=False),
        sa.Column('start_date', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('end_date', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('config_snapshot', JSONB, nullable=False),
        sa.Column('result', JSONB, nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('weights_set_id', sa.Integer(), nullable=True),
        sa.Column('optuna_study_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('idx_runs_type_status', 'runs', ['run_type', 'status'])
    op.create_index('idx_runs_started_at', 'runs', [sa.text('started_at DESC')])
    op.create_index('idx_runs_environment', 'runs', ['environment'])
    op.create_index('idx_runs_symbol', 'runs', ['symbol'])

    # Update foreign key references in other tables to use INTEGER
    # indicators_values
    op.execute("ALTER TABLE indicators_values ALTER COLUMN run_id TYPE INTEGER USING NULL")
    op.create_foreign_key('fk_indicators_values_run_id', 'indicators_values', 'runs', ['run_id'], ['id'])

    # signals
    op.execute("ALTER TABLE signals ALTER COLUMN run_id TYPE INTEGER USING NULL")
    op.create_foreign_key('fk_signals_run_id', 'signals', 'runs', ['run_id'], ['id'])

    # orders
    op.execute("ALTER TABLE orders ALTER COLUMN run_id TYPE INTEGER USING NULL")
    op.create_foreign_key('fk_orders_run_id', 'orders', 'runs', ['run_id'], ['id'])

    # trades
    op.execute("ALTER TABLE trades ALTER COLUMN run_id TYPE INTEGER USING NULL")
    op.create_foreign_key('fk_trades_run_id', 'trades', 'runs', ['run_id'], ['id'])

    # errors_log
    op.execute("ALTER TABLE errors_log ALTER COLUMN run_id TYPE INTEGER USING NULL")
    op.create_foreign_key('fk_errors_log_run_id', 'errors_log', 'runs', ['run_id'], ['id'])

    # optuna_studies
    op.execute("ALTER TABLE optuna_studies ALTER COLUMN run_id TYPE INTEGER USING NULL")
    op.create_foreign_key('fk_optuna_studies_run_id', 'optuna_studies', 'runs', ['run_id'], ['id'])


def downgrade() -> None:
    # Reverse the changes (not implemented for this migration)
    pass
