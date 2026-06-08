"""update_trades_for_ongoing_tracking

Revision ID: 007
Revises: 006
Create Date: 2026-06-08 15:00:00.000000

Modifies the trades table to support tracking ongoing (open) trades:
- Add 'status' column to distinguish open vs closed trades
- Make exit-related fields nullable (exit_price, closed_at, etc.)
- Set commission_total default to 0 (will accumulate entry + exit)

This allows creating trade entries when positions open,
then updating them when positions close.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add status column and make exit fields nullable."""

    # Add status column (default 'open' for new trades)
    op.add_column(
        'trades',
        sa.Column('status', sa.String(20), nullable=False, server_default='open', comment='open, closed')
    )
    op.create_index('idx_trades_status', 'trades', ['status'])

    # Make exit_order_id nullable (it's NULL when trade is still open)
    op.alter_column('trades', 'exit_order_id', nullable=True)

    # Make exit_price nullable
    op.alter_column('trades', 'exit_price', nullable=True)

    # Make closed_at nullable
    op.alter_column('trades', 'closed_at', nullable=True)

    # Make duration_seconds nullable
    op.alter_column('trades', 'duration_seconds', nullable=True)

    # Make pnl nullable (calculated only when trade closes)
    op.alter_column('trades', 'pnl', nullable=True)

    # Make pnl_percent nullable
    op.alter_column('trades', 'pnl_percent', nullable=True)

    # Set commission_total default to 0 (will accumulate entry + exit commission)
    op.alter_column(
        'trades',
        'commission_total',
        nullable=False,
        server_default=sa.text('0')
    )


def downgrade() -> None:
    """Revert trades table to original schema (closed trades only)."""

    # WARNING: This will delete all open trades!
    # Delete open trades before reverting schema
    op.execute("DELETE FROM trades WHERE status = 'open'")

    # Remove server_default from commission_total
    op.alter_column('trades', 'commission_total', server_default=None)

    # Make fields NOT NULL again
    op.alter_column('trades', 'pnl_percent', nullable=False)
    op.alter_column('trades', 'pnl', nullable=False)
    op.alter_column('trades', 'duration_seconds', nullable=False)
    op.alter_column('trades', 'closed_at', nullable=False)
    op.alter_column('trades', 'exit_price', nullable=False)
    op.alter_column('trades', 'exit_order_id', nullable=False)

    # Drop index and column
    op.drop_index('idx_trades_status', 'trades')
    op.drop_column('trades', 'status')
