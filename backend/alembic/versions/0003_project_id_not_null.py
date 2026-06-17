"""project_id NOT NULL — backfill Phase 1 null-project rows and constrain

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-17
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create a default project for Phase 1 data, backfill, then add NOT NULL.
    # A DO $$ block is used so the generated UUID from the INSERT is available
    # in the same transaction for the UPDATE statements.
    op.execute("""
    DO $$
    DECLARE
        default_id UUID;
    BEGIN
        INSERT INTO projects (name, description, created_at)
        VALUES ('Default Project', 'Migrated from Phase 1 null-project traces', NOW())
        RETURNING id INTO default_id;

        UPDATE traces SET project_id = default_id WHERE project_id IS NULL;
        UPDATE chunks SET project_id = default_id WHERE project_id IS NULL;
    END $$;
    """)
    op.execute("ALTER TABLE traces ALTER COLUMN project_id SET NOT NULL")
    op.execute("ALTER TABLE chunks ALTER COLUMN project_id SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE traces ALTER COLUMN project_id DROP NOT NULL")
    op.execute("ALTER TABLE chunks ALTER COLUMN project_id DROP NOT NULL")
