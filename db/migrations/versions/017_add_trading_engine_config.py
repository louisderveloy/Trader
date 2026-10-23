"""add trading_engine to config

Adds default trading engine configuration ('indicators' vs 'predictive_model')
to the config JSONB blob in the config table.

Revision ID: 017
Revises: 016
Create Date: 2026-10-23

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add default trading_engine section to existing config rows if absent."""
    op.execute("""
        UPDATE config
        SET config = jsonb_set(
            config,
            '{trading_engine}',
            '{"engine_type": "indicators"}'::jsonb,
            true
        )
        WHERE NOT (config ? 'trading_engine');
    """)


def downgrade() -> None:
    """Remove trading_engine section from config rows."""
    op.execute("""
        UPDATE config
        SET config = config - 'trading_engine'
        WHERE config ? 'trading_engine';
    """)
