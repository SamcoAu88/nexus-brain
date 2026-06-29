"""Add Row-Level Security (RLS) policies for user isolation

Enables PostgreSQL RLS on all user-scoped tables so that even direct
database queries respect user boundaries.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-29 19:15:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables with user_id column that need RLS
RLS_TABLES = [
    ("user_profiles", "user_id"),
    ("collections", "user_id"),
    ("conversations", "user_id"),
    ("entities", "user_id"),
    ("cost_tracking", "user_id"),
    ("audit_logs", "user_id"),
    ("pii_redaction_logs", "user_id"),
]


def upgrade() -> None:
    """Enable RLS on all user-scoped tables."""

    for table, id_col in RLS_TABLES:
        # 1. Enable RLS
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

        # 2. Create policy: user can only see their own rows
        #    The current_user_id is set by the application via SET SESSION
        op.execute(f"""
            CREATE POLICY user_isolation_{table} ON {table}
            FOR ALL
            USING ({id_col} = current_setting('app.current_user_id')::uuid)
            WITH CHECK ({id_col} = current_setting('app.current_user_id')::uuid)
        """)

    # 3. Grant usage to app role (adjust for your DB user)
    op.execute("GRANT USAGE ON SCHEMA public TO CURRENT_USER")

    # 4. Create helper function to set user context
    op.execute("""
        CREATE OR REPLACE FUNCTION set_current_user_id(user_uuid uuid)
        RETURNS void AS $$
        BEGIN
            PERFORM set_config('app.current_user_id', user_uuid::text, false);
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER
    """)


def downgrade() -> None:
    """Disable RLS and drop policies."""

    op.execute("DROP FUNCTION IF EXISTS set_current_user_id(uuid)")

    for table, _ in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS user_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
