"""add_grafana_readonly_role

Revision ID: 012
Revises: 011
Create Date: 2026-06-10 00:30:00.000000

Creates a dedicated, SELECT-only PostgreSQL role for the external Grafana
connection so a Grafana credential compromise cannot write to privileged
tables such as ``run_commands`` (security review Finding #6).

The role's password is read from ``POSTGRES_GRAFANA_READONLY_PASSWORD``. When
that variable is absent (e.g. local dev without Grafana), the role is created
with NOLOGIN so the migration stays idempotent and no weak default is baked in;
an operator can set a password later with ``ALTER ROLE ... LOGIN PASSWORD ...``.
"""

import os

from alembic import op

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def _sql_quote(value: str) -> str:
    """Escape a string literal for safe inline use in SQL (double single-quotes)."""
    return value.replace("'", "''")


def upgrade() -> None:
    """Create the grafana_readonly role with SELECT-only privileges."""
    password = os.getenv('POSTGRES_GRAFANA_READONLY_PASSWORD')
    role_name = os.getenv('POSTGRES_GRAFANA_READONLY_USER')

    if password:
        login_clause = f"LOGIN PASSWORD '{_sql_quote(password)}'"
    else:
        # No password supplied: create the role but disable login until an
        # operator sets credentials explicitly. Avoids hardcoding a secret.
        login_clause = "NOLOGIN"

    # Create the role if it does not already exist (roles are cluster-global).
    op.execute(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role_name}') THEN
                CREATE ROLE {role_name} {login_clause};
            END IF;
        END
        $$;
    """)

    # Grant read-only access to the current database/schema.
    db_name = os.getenv('POSTGRES_DB', 'trader_bot')
    op.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO {role_name};')
    op.execute(f"GRANT USAGE ON SCHEMA public TO {role_name};")
    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {role_name};")
    op.execute(f"GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO {role_name};")

    # Future tables created by the migration role inherit SELECT for grafana.
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
               f"GRANT SELECT ON TABLES TO {role_name};")

    # Defense in depth: explicitly revoke any write capability.
    op.execute(f"REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {role_name};")


def downgrade() -> None:
    """Revoke privileges and drop the role."""
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM {ROLE_NAME};")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ROLE_NAME};")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ROLE_NAME};")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {ROLE_NAME};")
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{ROLE_NAME}') THEN
                EXECUTE 'REVOKE CONNECT ON DATABASE ' || quote_ident(current_database()) || ' FROM {ROLE_NAME}';
                DROP ROLE {ROLE_NAME};
            END IF;
        END
        $$;
    """)
