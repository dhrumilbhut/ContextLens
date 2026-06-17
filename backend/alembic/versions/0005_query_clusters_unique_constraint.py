"""add unique constraint to query_clusters

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-17
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE query_clusters
        ADD CONSTRAINT uq_cluster_project_label UNIQUE (project_id, cluster_label)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE query_clusters
        DROP CONSTRAINT IF EXISTS uq_cluster_project_label
    """)
