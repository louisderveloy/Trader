"""Add config update notification trigger

Revision ID: 008
Revises: 007
Create Date: 2026-06-08

This migration adds a PostgreSQL trigger and notification function
that broadcasts config changes to all listening bot instances.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """Add trigger function and trigger for config updates."""

    # Create the notification function
    op.execute("""
        CREATE OR REPLACE FUNCTION notify_config_updated()
        RETURNS trigger AS $$
        BEGIN
            -- Notify all listeners about the config update
            -- Send the new config as JSON payload
            PERFORM pg_notify(
                'config_updated',
                json_build_object(
                    'id', NEW.id::text,
                    'config', NEW.config,
                    'updated_at', NEW.updated_at::text
                )::text
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger on config table for INSERT and UPDATE
    op.execute("""
        CREATE TRIGGER on_config_updated
        AFTER INSERT OR UPDATE ON config
        FOR EACH ROW
        EXECUTE FUNCTION notify_config_updated();
    """)


def downgrade():
    """Remove trigger and function."""

    # Drop trigger
    op.execute("DROP TRIGGER IF EXISTS on_config_updated ON config;")

    # Drop function
    op.execute("DROP FUNCTION IF EXISTS notify_config_updated();")
