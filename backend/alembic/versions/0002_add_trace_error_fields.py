"""add error_message and failed_at to traces

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-16
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE traces ADD COLUMN IF NOT EXISTS error_message TEXT")
    op.execute("ALTER TABLE traces ADD COLUMN IF NOT EXISTS failed_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE traces DROP COLUMN IF EXISTS error_message")
    op.execute("ALTER TABLE traces DROP COLUMN IF EXISTS failed_at")
