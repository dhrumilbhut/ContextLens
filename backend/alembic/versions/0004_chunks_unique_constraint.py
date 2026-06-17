"""add missing UNIQUE(project_id, content_hash) constraint to chunks

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-17

This constraint was specified in DATA_MODEL.md but omitted from migration 0001.
It is required for the ON CONFLICT (project_id, content_hash) DO NOTHING clause
in chunk_service.get_or_create_chunk() to work. The Phase 1 workaround (manual
SELECT + INSERT for null project_ids) masked the absence of this constraint.
Now that project_id is NOT NULL (migration 0003), ON CONFLICT is the correct
deduplication path and the constraint must exist.
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chunks ADD CONSTRAINT chunks_project_content_hash_unique UNIQUE (project_id, content_hash)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chunks_project_content_hash_unique"
    )
