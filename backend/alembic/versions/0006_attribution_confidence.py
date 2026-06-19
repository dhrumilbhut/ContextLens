"""Add attribution_confidence column to claims; backfill from existing attribution_score.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-19

Three-state attribution model:
  'high' — attribution_score >= 0.75 (well-attributed, existing behavior)
  'low'  — attribution_score >= 0.65 and < 0.75 (attributed but uncertain)
  NULL   — no attribution found (attribution_score is NULL), retrieval failure

The column is additive — existing rows are backfilled based on their stored
attribution_score so all prior data is correctly classified retroactively.
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE claims ADD COLUMN attribution_confidence TEXT"
    )

    # Backfill existing high-confidence attributions
    op.execute("""
        UPDATE claims
        SET attribution_confidence = 'high'
        WHERE attribution_score >= 0.75
    """)

    # Backfill rows that fall in the new low-confidence band.
    # Prior to this migration, scores in 0.65–0.75 returned (None, None) from
    # attribute_claim(), so attributed_chunk_id was NULL for those rows too.
    # Any stored attribution_score in this band (if any) was recorded but the
    # chunk link was not set — this UPDATE covers that edge case in case any
    # such rows exist from early pipeline iterations.
    op.execute("""
        UPDATE claims
        SET attribution_confidence = 'low'
        WHERE attribution_score >= 0.65 AND attribution_score < 0.75
    """)
    # Rows with NULL attribution_score keep attribution_confidence = NULL (retrieval failure).


def downgrade() -> None:
    op.execute("ALTER TABLE claims DROP COLUMN attribution_confidence")
