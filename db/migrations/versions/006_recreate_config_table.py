"""recreate_config_table

Revision ID: 006
Revises: 005
Create Date: 2026-06-08 00:30:00.000000

Drop and recreate config table with simplified structure.
Single row containing all configuration as a JSON blob instead of key-value pairs.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old config table
    op.drop_table('config')

    # Create new config table with simplified structure
    op.create_table(
        'config',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('config', JSONB, nullable=False, comment='Complete configuration as JSON blob'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()'))
    )


def downgrade() -> None:
    # Drop the new table
    op.drop_table('config')

    # Recreate the old structure
    op.create_table(
        'config',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('value', JSONB, nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('category', 'key', name='uq_config_category_key')
    )

    op.create_index('idx_config_category', 'config', ['category'])
    op.create_index('idx_config_category_key', 'config', ['category', 'key'])
