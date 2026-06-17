import asyncio
import logging

import asyncpg

from app.config import settings
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def reprocess_pending_traces():
    asyncio.run(_reprocess_pending_traces())


async def _reprocess_pending_traces():
    # Lazy import avoids a potential circular dependency at module load time.
    from app.worker.tasks import process_trace

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        # Only re-enqueue traces from previous days. Today's pending traces may
        # still be within the daily limit and will be processed normally.
        rows = await conn.fetch(
            """
            SELECT id::text
            FROM traces
            WHERE status = 'pending'
              AND created_at < CURRENT_DATE
            """
        )
        if not rows:
            logger.info("reprocess pending: no stuck traces found")
            return

        for row in rows:
            process_trace.delay(row["id"])

        logger.info(f"reprocess pending: enqueued {len(rows)} stuck traces")
    finally:
        await conn.close()


@celery_app.task
def cluster_project_queries_all():
    asyncio.run(_cluster_project_queries_all())


async def _cluster_project_queries_all():
    from app.worker.clustering import cluster_project_queries

    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        projects = await conn.fetch("SELECT id::text FROM projects")
        for p in projects:
            try:
                await cluster_project_queries(conn, p["id"])
            except Exception as exc:
                logger.error(f"clustering failed for project {p['id']}: {exc}")
    finally:
        await conn.close()


@celery_app.task
def check_for_volume_spikes():
    asyncio.run(_check_for_volume_spikes())


async def _check_for_volume_spikes():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    try:
        rows = await conn.fetch(
            """
            SELECT u.project_id::text, u.traces_ingested AS today_count, history.avg_7d
            FROM usage_records u
            JOIN (
                SELECT project_id, AVG(traces_ingested) AS avg_7d
                FROM usage_records
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY project_id
            ) history USING (project_id)
            WHERE u.date = CURRENT_DATE
              AND u.traces_ingested > history.avg_7d * 5
              AND u.traces_ingested > 500
            """
        )

        if not rows:
            logger.info("volume spike check: no anomalies found")
            return

        for row in rows:
            await conn.execute(
                """
                UPDATE usage_records
                SET flagged = TRUE, flag_reason = 'volume_spike', updated_at = NOW()
                WHERE project_id = $1::uuid AND date = CURRENT_DATE
                """,
                row["project_id"],
            )
            logger.warning(
                f"volume spike detected for project {row['project_id']}: "
                f"{row['today_count']} traces today vs {row['avg_7d']:.0f} avg"
            )
    finally:
        await conn.close()
