"""add stop_loss_price, take_profit_price and exit_reason to trades

Issue #17: the trades table previously stored neither the stop-loss / take-profit
levels a position was opened with, nor *why* it was closed. The exit reason was
computed at runtime but discarded before persistence, and the SL/TP levels lived
only in the in-memory position dict. This made it impossible to audit on the
dashboard whether a -8% loss came from a stop-loss that fired late, a signal exit,
or a take-profit — or to verify that the configured SL/TP was actually applied.

Adds three nullable columns to ``trades``:
- ``stop_loss_price``   : SL level the position was opened with.
- ``take_profit_price`` : TP level the position was opened with.
- ``exit_reason``       : why the position closed ('stop_loss', 'take_profit',
                          'signal', 'end_of_period', ...). NULL while open.

All nullable / additive; nothing is deleted (DB rule: rien n'est jamais supprimé).

Revision ID: 016
Revises: 015
Create Date: 2026-06-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add SL/TP level and exit_reason columns to trades."""
    op.add_column(
        'trades',
        sa.Column('stop_loss_price', sa.DECIMAL(20, 8), nullable=True,
                  comment='Stop-loss level the position was opened with'),
    )
    op.add_column(
        'trades',
        sa.Column('take_profit_price', sa.DECIMAL(20, 8), nullable=True,
                  comment='Take-profit level the position was opened with'),
    )
    op.add_column(
        'trades',
        sa.Column('exit_reason', sa.String(20), nullable=True,
                  comment='Why the trade closed: stop_loss, take_profit, signal, end_of_period'),
    )


def downgrade() -> None:
    """Remove the columns added in this migration."""
    op.drop_column('trades', 'exit_reason')
    op.drop_column('trades', 'take_profit_price')
    op.drop_column('trades', 'stop_loss_price')
