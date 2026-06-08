"""Drop notifications_log table

Revision ID: 009
Revises: 008
Create Date: 2026-06-09

Removes the notifications_log table as notification logging is redundant
with Discord channel history.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop notifications_log table and its indexes."""
    # Drop indexes first
    op.drop_index('idx_notifications_type', table_name='notifications_log')
    op.drop_index('idx_notifications_sent_at', table_name='notifications_log')

    # Drop table
    op.drop_table('notifications_log')


def downgrade() -> None:
    """Recreate notifications_log table if needed."""
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import JSONB, UUID

    op.create_table(
        'notifications_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('sent_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('status', sa.String(20), nullable=False, comment='sent, failed'),
        sa.Column('metadata', JSONB, nullable=True)
    )
    op.create_index('idx_notifications_sent_at', 'notifications_log', [sa.text('sent_at DESC')])
    op.create_index('idx_notifications_type', 'notifications_log', ['notification_type'])
