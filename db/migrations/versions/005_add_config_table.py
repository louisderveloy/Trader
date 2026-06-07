"""add_config_table

Revision ID: 005
Revises: 7f964c375235
Create Date: 2026-06-08 00:00:00.000000

Adds config table for persistent storage of runtime configuration changes.
This allows configuration updates made via API to survive bot restarts.

The table uses a key-value structure with categories for organization:
- category: strategy, risk, binance, stop_loss_take_profit
- key: specific config parameter name
- value: JSONB for flexibility (supports any type)
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '7f964c375235'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================
    # Table: config
    # ==========================================
    op.create_table(
        'config',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('category', sa.String(50), nullable=False, comment='Config category: strategy, risk, binance, etc.'),
        sa.Column('key', sa.String(100), nullable=False, comment='Config parameter name'),
        sa.Column('value', JSONB, nullable=False, comment='Config value (any type)'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('category', 'key', name='uq_config_category_key')
    )

    # Index for fast lookups by category
    op.create_index('idx_config_category', 'config', ['category'])

    # Index for fast lookups by category + key
    op.create_index('idx_config_category_key', 'config', ['category', 'key'])


def downgrade() -> None:
    op.drop_table('config')
