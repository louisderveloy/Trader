"""add_score_logs_table

Revision ID: 010
Revises: 009
Create Date: 2026-06-09 00:00:00.000000

Creates score_logs table for tracking every score calculation.
This table is used for statistical analysis and performance tracking,
logging all weighted scores computed by the strategy engine.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create score_logs table."""

    op.create_table(
        'score_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', sa.Integer(), nullable=False, comment='Reference to the run'),
        sa.Column('config_id', UUID(as_uuid=True), nullable=False, comment='Config active at calculation time'),
        sa.Column('weights_set_id', UUID(as_uuid=True), nullable=False, comment='Weights set used in calculation'),
        sa.Column('order_id', UUID(as_uuid=True), nullable=True, comment='Order created from this score, null if no order'),
        sa.Column('time', sa.TIMESTAMP(timezone=True), nullable=False, comment='Timestamp of the score calculation'),
        sa.Column('symbol', sa.String(20), nullable=False, comment='Trading pair symbol'),
        sa.Column('weighted_score', sa.DECIMAL(5, 4), nullable=False, comment='Calculated weighted score [-1, 1]'),
        sa.Column('indicators_snapshot', JSONB, nullable=False, comment='Snapshot of all indicator values'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['run_id'], ['runs.id'], name='fk_score_logs_run_id'),
        sa.ForeignKeyConstraint(['config_id'], ['config.id'], name='fk_score_logs_config_id'),
        sa.ForeignKeyConstraint(['weights_set_id'], ['weights_sets.id'], name='fk_score_logs_weights_set_id'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name='fk_score_logs_order_id')
    )

    # Indexes for efficient querying
    op.create_index('idx_score_logs_run_time', 'score_logs', ['run_id', 'time'])
    op.create_index('idx_score_logs_config', 'score_logs', ['config_id'])
    op.create_index('idx_score_logs_weights_set', 'score_logs', ['weights_set_id'])
    op.create_index('idx_score_logs_symbol', 'score_logs', ['symbol', sa.text('time DESC')])
    op.create_index('idx_score_logs_created_at', 'score_logs', [sa.text('created_at DESC')])
    # Index for finding scores that resulted in orders
    op.create_index('idx_score_logs_order_id', 'score_logs', ['order_id'], postgresql_where=sa.text('order_id IS NOT NULL'))


def downgrade() -> None:
    """Drop score_logs table."""

    op.drop_table('score_logs')
