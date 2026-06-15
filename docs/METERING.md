# Metering & Abuse Prevention

Usage tracking and rate limiting for the self-hosted version.

---

## Goals

1. **Track processing volume per project** — know how much LLM cost is being incurred
2. **Prevent accidental abuse** — a bug in the developer's code could send millions
   of traces in a loop; we should detect and stop that
3. **Never break the developer's RAG app** — limits affect processing, not ingestion

---

## What We Meter

Two numbers, tracked per project per day:

```
traces_ingested    — how many traces the SDK sent to POST /ingest
traces_processed   — how many actually ran through the LLM attribution pipeline
```

**Why both?**
When a project hits the processing limit, we still accept traces (RAG app gets no errors)
but don't process them. `traces_ingested` keeps going up, `traces_processed` stops.
This distinction lets us identify: is the RAG app still sending even after being blocked?

---

## Limits (Self-Hosted)

These are defaults. All configurable via `.env`.

```bash
DAILY_PROCESSING_LIMIT=10000    # traces processed per project per day
HOURLY_INGEST_RATE_LIMIT=1000   # traces ingested per project per hour
PER_MINUTE_RATE_LIMIT=100       # traces per project per minute (burst protection)
```

**Why have limits at all on a self-hosted tool?**

Because you are paying for the LLM API calls. If someone runs a misconfigured
load test or an infinite loop against their local ContextLens instance, they
could rack up significant OpenAI charges. These limits are protecting the
developer's own wallet, not a cloud service.

Set `DAILY_PROCESSING_LIMIT=0` to disable limits entirely if preferred.

---

## Rate Limiting (Redis)

Three time windows, checked on every ingest request:

```python
async def check_rate_limits(project_id: str):
    now = time.time()

    # per-minute window
    minute_key = f"ratelimit:{project_id}:minute:{int(now // 60)}"
    minute_count = await redis.incr(minute_key)
    await redis.expire(minute_key, 120)
    if minute_count > settings.PER_MINUTE_RATE_LIMIT:
        raise RateLimitError("Rate limit exceeded: too many requests per minute")

    # per-hour window
    hour_key = f"ratelimit:{project_id}:hour:{int(now // 3600)}"
    hour_count = await redis.incr(hour_key)
    await redis.expire(hour_key, 7200)
    if hour_count > settings.HOURLY_INGEST_RATE_LIMIT:
        raise RateLimitError("Rate limit exceeded: too many requests per hour")
```

Redis `INCR` + `EXPIRE` is atomic — no race conditions between concurrent requests.
Microsecond latency — doesn't add meaningful overhead to the ingest path.

---

## Daily Processing Limit

Checked before enqueuing each trace for processing:

```python
async def handle_ingest(payload, project_id: str):
    # 1. rate limiting (Redis — fast, in memory)
    await check_rate_limits(project_id)

    # 2. daily limit check (Postgres)
    usage = await get_or_create_usage_record(project_id, today())
    processing_blocked = (
        settings.DAILY_PROCESSING_LIMIT > 0
        and usage.traces_processed >= settings.DAILY_PROCESSING_LIMIT
    )

    # 3. store trace (always — never reject ingestion)
    trace = await db.create_trace(...payload, project_id=project_id)

    # 4. increment ingested counter (always)
    await db.increment_usage(project_id, today(), ingested=1)

    # 5. enqueue only if not blocked
    if not processing_blocked:
        await redis.enqueue_job(trace.id)
        await db.increment_usage(project_id, today(), processed=1)
    else:
        # trace sits as "pending" — will not be processed until limit resets
        logger.warning(f"Daily processing limit reached for project {project_id}")

    return {"trace_id": trace.id, "status": "pending"}
```

---

## Abuse Detection

Beyond hard limits, we flag suspicious usage patterns:

### Volume Spike Detection

A scheduled Celery beat task runs hourly:

```python
@celery.task
async def check_for_volume_spikes():
    # flag projects whose today count is 5x their 7-day average
    # and above an absolute minimum (ignores tiny projects)
    suspicious = await db.fetchall("""
        SELECT project_id, traces_ingested as today_count, avg_7d
        FROM usage_records u
        JOIN (
            SELECT project_id, AVG(traces_ingested) as avg_7d
            FROM usage_records
            WHERE date >= NOW() - INTERVAL '7 days'
            GROUP BY project_id
        ) history USING (project_id)
        WHERE date = CURRENT_DATE
          AND traces_ingested > avg_7d * 5
          AND traces_ingested > 500
    """)

    for row in suspicious:
        await db.flag_usage_record(
            row.project_id, today(), reason="volume_spike"
        )
        logger.warning(
            f"Volume spike detected for project {row.project_id}: "
            f"{row.today_count} traces today vs {row.avg_7d:.0f} avg"
        )
```

Flagging writes `flagged = true` and `flag_reason` to `usage_records`.
It does not automatically block processing — it just surfaces the anomaly
in the usage dashboard so the developer can investigate.

---

## The `usage_records` Table

```sql
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
);
```

### Safe Concurrent Increment

Multiple ingest requests arrive simultaneously. We use upsert to increment
without race conditions:

```sql
INSERT INTO usage_records (project_id, date, traces_ingested)
VALUES (:project_id, :date, 1)
ON CONFLICT (project_id, date) DO UPDATE
SET traces_ingested = usage_records.traces_ingested + 1,
    updated_at = NOW();
```

This is atomic in Postgres — no two concurrent requests can both read
the same value and both increment it independently.

---

## Usage View in Dashboard

The project settings page shows:

```
┌────────────────────────────────────────────────────────┐
│  Usage — June 2026                                      │
├────────────────────────────────────────────────────────┤
│  Today: 847 / 10,000 processed (8.5%)                  │
│  ████░░░░░░░░░░░░░░░░░░░░░░  8.5%                     │
│                                                        │
│  Limit resets: tomorrow at midnight                    │
│  To raise the limit: set DAILY_PROCESSING_LIMIT in .env│
│                                                        │
│  Last 7 days:                                          │
│  [bar chart of daily trace counts]                     │
└────────────────────────────────────────────────────────┘
```

---

## Cloud Migration

When the cloud version is added, metering moves from per-project to per-user,
and limits become per-plan rather than per `.env` config:

```python
# self-hosted (now)
DAILY_PROCESSING_LIMIT = settings.DAILY_PROCESSING_LIMIT  # from .env

# cloud (later)
PLAN_LIMITS = {
    "free":       10_000,   # per month
    "pro":        50_000,
    "team":      200_000,
    "enterprise": None      # unlimited
}
DAILY_PROCESSING_LIMIT = PLAN_LIMITS[user.plan] // 30
```

The metering infrastructure (usage_records table, increment logic,
rate limiting) doesn't change. Only the limit source changes.
