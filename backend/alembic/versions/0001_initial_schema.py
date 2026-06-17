"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-16
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector extension — required for vector(1536) column type and ivfflat index
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute("""
        CREATE TABLE projects (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT NOT NULL,
            description TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE api_keys (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            key_hash     TEXT NOT NULL UNIQUE,
            key_prefix   TEXT NOT NULL,
            name         TEXT NOT NULL,
            last_used_at TIMESTAMPTZ,
            revoked_at   TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # project_id is nullable in Phase 1 — Phase 2 adds project scoping and makes it NOT NULL.
    # See build-log.md for the reasoning behind this deviation from DATA_MODEL.md.
    op.execute("""
        CREATE TABLE traces (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id       UUID REFERENCES projects(id) ON DELETE CASCADE,
            query_text       TEXT NOT NULL,
            query_embedding  vector(1536),
            retrieved_chunks JSONB NOT NULL,
            llm_response     TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'pending',
            latency_ms       INTEGER,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_traces_project_id ON traces(project_id)")
    op.execute("CREATE INDEX idx_traces_created_at ON traces(created_at DESC)")
    op.execute("CREATE INDEX idx_traces_status ON traces(status)")

    # project_id nullable for same reason as traces — Phase 2 will enforce it.
    op.execute("""
        CREATE TABLE chunks (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id      UUID REFERENCES projects(id) ON DELETE CASCADE,
            content         TEXT NOT NULL,
            content_hash    TEXT NOT NULL,
            source_document TEXT NOT NULL,
            chunk_index     INTEGER,
            embedding       vector(1536) NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_chunks_project_id ON chunks(project_id)")

    # IVFFlat approximate nearest-neighbor index for cosine similarity search.
    # lists=100 is a reasonable default — tune upward if the corpus grows large.
    # Creating on an empty table is fine; the index builds structure without data.
    op.execute("""
        CREATE INDEX idx_chunks_embedding ON chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    op.execute("""
        CREATE TABLE claims (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trace_id             UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
            claim_text           TEXT NOT NULL,
            claim_index          INTEGER NOT NULL,
            attributed_chunk_id  UUID REFERENCES chunks(id),
            attribution_score    FLOAT,
            faithfulness_verdict TEXT,
            faithfulness_score   FLOAT,
            is_faithful          BOOLEAN,
            judge_reasoning      TEXT,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_claims_trace_id ON claims(trace_id)")
    op.execute("CREATE INDEX idx_claims_attributed_chunk ON claims(attributed_chunk_id)")
    op.execute("CREATE INDEX idx_claims_is_faithful ON claims(is_faithful)")

    op.execute("""
        CREATE TABLE query_clusters (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            cluster_label       TEXT NOT NULL,
            centroid_embedding  vector(1536) NOT NULL,
            avg_faithfulness    FLOAT NOT NULL,
            trace_count         INTEGER NOT NULL DEFAULT 0,
            unfaithful_count    INTEGER NOT NULL DEFAULT 0,
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("CREATE INDEX idx_clusters_project_id ON query_clusters(project_id)")

    op.execute("""
        CREATE TABLE usage_records (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id         UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            date               DATE NOT NULL,
            traces_ingested    INTEGER NOT NULL DEFAULT 0,
            traces_processed   INTEGER NOT NULL DEFAULT 0,
            flagged            BOOLEAN NOT NULL DEFAULT FALSE,
            flag_reason        TEXT,
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(project_id, date)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_records")
    op.execute("DROP TABLE IF EXISTS query_clusters")
    op.execute("DROP TABLE IF EXISTS claims")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS traces")
    op.execute("DROP TABLE IF EXISTS api_keys")
    op.execute("DROP TABLE IF EXISTS projects")
    op.execute("DROP EXTENSION IF EXISTS vector")
