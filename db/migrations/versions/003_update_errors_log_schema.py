"""update_errors_log_schema

Revision ID: 003
Revises: 002
Create Date: 2026-06-05 22:00:00.000000

Aligns errors_log table schema with Python code (bot/runs/errors.py):
- Add severity column (VARCHAR 20)
- Rename error_type -> category
- Rename message -> error_message
- Rename stack_trace -> error_traceback
- Rename metadata -> context
- Rename occurred_at -> timestamp
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add severity column with default value
    op.add_column(
        'errors_log',
        sa.Column('severity', sa.String(20), nullable=False, server_default='medium')
    )

    # Rename columns to match Python code expectations
    op.alter_column('errors_log', 'error_type', new_column_name='category')
    op.alter_column('errors_log', 'message', new_column_name='error_message')
    op.alter_column('errors_log', 'stack_trace', new_column_name='error_traceback')
    op.alter_column('errors_log', 'metadata', new_column_name='context')
    op.alter_column('errors_log', 'occurred_at', new_column_name='timestamp')

    # Update index name (drop old, create new with renamed column)
    op.drop_index('idx_errors_occurred_at', table_name='errors_log')
    op.create_index('idx_errors_timestamp', 'errors_log', [sa.text('timestamp DESC')])

    # Add index on severity for filtering
    op.create_index('idx_errors_severity', 'errors_log', ['severity'])

    # Add index on category for filtering
    op.create_index('idx_errors_category', 'errors_log', ['category'])


def downgrade() -> None:
    # Drop new indexes
    op.drop_index('idx_errors_category', table_name='errors_log')
    op.drop_index('idx_errors_severity', table_name='errors_log')
    op.drop_index('idx_errors_timestamp', table_name='errors_log')

    # Rename columns back
    op.alter_column('errors_log', 'timestamp', new_column_name='occurred_at')
    op.alter_column('errors_log', 'context', new_column_name='metadata')
    op.alter_column('errors_log', 'error_traceback', new_column_name='stack_trace')
    op.alter_column('errors_log', 'error_message', new_column_name='message')
    op.alter_column('errors_log', 'category', new_column_name='error_type')

    # Drop severity column
    op.drop_column('errors_log', 'severity')

    # Recreate original index
    op.create_index('idx_errors_occurred_at', 'errors_log', [sa.text('occurred_at DESC')])
