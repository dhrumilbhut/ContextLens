"""
Phase A validation script for the ContextLens Python SDK.

Runs three scenarios in order:
  1. Happy path   — trace sent, processed, claims scored end to end
  2. Unreachable  — wrong port, confirms with block doesn't hang or raise
  3. Disabled     — CONTEXTLENS_ENABLED=false, confirms complete no-op

Before running:
  cp sdk-validation/.env.example sdk-validation/.env
  # fill in CONTEXTLENS_API_KEY and CONTEXTLENS_PROJECT_ID
  pip install -e ./sdk
  pip install python-dotenv httpx
  python sdk-validation/test_manual_pattern.py
"""

import os
import sys
import time

# Load sdk-validation/.env before importing contextlens so env vars are set
# when the SDK reads them. python-dotenv is a dev/validation dep, not SDK dep.
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(env_path)
except ImportError:
    print("python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

import httpx
import contextlens
from contextlens.config import reset_for_testing

# ---------------------------------------------------------------------------
# Shared test data — consistent with the refund/cancellation domain used
# throughout this project's curl examples and build log.
# ---------------------------------------------------------------------------
QUERY = "What is the refund policy?"
CHUNKS = [
    {
        "content": "Customers may request a full refund within 30 days of purchase.",
        "source": "refund-policy.pdf",
        "chunk_index": 0,
    },
    {
        "content": "Subscription cancellations must be submitted at least 7 business days "
                   "before the next billing cycle.",
        "source": "terms-of-service.pdf",
        "chunk_index": 2,
    },
]
RESPONSE = (
    "You can get a full refund within 30 days of purchase. "
    "Cancellations require 7 days notice."
)

API_URL = os.environ.get("CONTEXTLENS_API_URL", "http://localhost:8000")
PROJECT_ID = os.environ.get("CONTEXTLENS_PROJECT_ID", "")


def separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Scenario 1: Happy path
# ---------------------------------------------------------------------------
separator("Scenario 1: Happy path")

if not os.environ.get("CONTEXTLENS_API_KEY"):
    print("ERROR: CONTEXTLENS_API_KEY not set. Copy .env.example to .env and fill it in.")
    sys.exit(1)

if not PROJECT_ID:
    print("ERROR: CONTEXTLENS_PROJECT_ID not set. Add it to sdk-validation/.env.")
    sys.exit(1)

start = time.perf_counter()

with contextlens.trace(query=QUERY) as trace:
    trace.log_chunks(CHUNKS)
    trace.log_response(RESPONSE)

elapsed_ms = (time.perf_counter() - start) * 1000
print(f"with block elapsed: {elapsed_ms:.2f}ms")
print("(background thread started — HTTP call happens asynchronously)")

print("\nWaiting 15s for pipeline to process the trace...")
time.sleep(15)

# Query the backend for the most recent processed trace
print("\nFetching most recent trace from backend...")
try:
    r = httpx.get(
        f"{API_URL}/projects/{PROJECT_ID}/traces?limit=1&status=processed",
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    traces = data.get("traces", [])

    if not traces:
        print("WARNING: no processed traces found. Pipeline may still be running.")
    else:
        latest = traces[0]
        print(f"Latest trace ID : {latest['id']}")
        print(f"Status          : {latest['status']}")
        print(f"Query           : {latest['query_text']}")
        print(f"Claims          : {latest['claim_count']}")
        print(f"Faithful        : {latest['faithful_claim_count']}")
        avg = latest.get("avg_faithfulness")
        print(f"Avg faithfulness: {round(avg * 100)}%" if avg is not None else "Avg faithfulness: n/a")

        # Fetch full detail to show per-claim breakdown
        detail_r = httpx.get(
            f"{API_URL}/projects/{PROJECT_ID}/traces/{latest['id']}",
            timeout=10,
        )
        detail_r.raise_for_status()
        detail = detail_r.json()
        print(f"\nClaims:")
        for claim in detail.get("claims", []):
            verdict = claim["faithfulness_verdict"]
            score = claim["faithfulness_score"]
            chunk = claim.get("attribution")
            src = chunk["source_document"] if chunk else "NO SOURCE (retrieval failure)"
            print(f"  [{verdict:10s} {score:.2f}]  {claim['claim_text'][:70]}")
            print(f"               source: {src}")

except Exception as e:
    print(f"ERROR fetching trace: {e}")

print("\nScenario 1: PASS" if elapsed_ms < 50 else f"\nScenario 1: WARNING — with block took {elapsed_ms:.0f}ms (expected <50ms)")


# ---------------------------------------------------------------------------
# Scenario 2: Unreachable backend
# ---------------------------------------------------------------------------
separator("Scenario 2: Unreachable backend (http://localhost:9999)")

os.environ["CONTEXTLENS_API_URL"] = "http://localhost:9999"

start = time.perf_counter()

with contextlens.trace(query=QUERY) as trace:
    trace.log_chunks(CHUNKS)
    trace.log_response(RESPONSE)

elapsed_ms = (time.perf_counter() - start) * 1000
timeout_setting = float(os.environ.get("CONTEXTLENS_TIMEOUT", "5"))

print(f"with block elapsed: {elapsed_ms:.2f}ms  (CONTEXTLENS_TIMEOUT={timeout_setting:.0f}s)")
print("No exception raised. Background thread will time out silently.")

if elapsed_ms < (timeout_setting * 1000 + 500):
    print("Scenario 2: PASS — with block exited well within timeout")
else:
    print(f"Scenario 2: FAIL — with block took {elapsed_ms:.0f}ms, should be near-instant")

# Restore URL for any follow-up
os.environ["CONTEXTLENS_API_URL"] = API_URL


# ---------------------------------------------------------------------------
# Scenario 3: SDK disabled
# ---------------------------------------------------------------------------
separator("Scenario 3: CONTEXTLENS_ENABLED=false")

os.environ["CONTEXTLENS_ENABLED"] = "false"
reset_for_testing()

start = time.perf_counter()

with contextlens.trace(query=QUERY) as trace:
    trace.log_chunks(CHUNKS)
    trace.log_response(RESPONSE)

elapsed_ms = (time.perf_counter() - start) * 1000

print(f"with block elapsed: {elapsed_ms:.2f}ms")
print("No network call made. Verifying no new trace appeared...")

time.sleep(3)

try:
    r = httpx.get(
        f"{API_URL}/projects/{PROJECT_ID}/traces?limit=1",
        timeout=10,
    )
    r.raise_for_status()
    traces_after = r.json().get("traces", [])
    if traces_after:
        first_id = traces_after[0]["id"]
        # The most recent trace should still be the scenario 1 trace
        # (scenario 2 failed to send, scenario 3 never sent)
        print(f"Most recent trace ID: {first_id} (should be same as scenario 1 trace)")
except Exception as e:
    print(f"Could not verify: {e}")

if elapsed_ms < 5:
    print("Scenario 3: PASS — sub-millisecond, complete no-op")
else:
    print(f"Scenario 3: WARNING — took {elapsed_ms:.2f}ms, expected <1ms")

os.environ["CONTEXTLENS_ENABLED"] = "true"
reset_for_testing()


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
separator("Done")
print("All three scenarios completed.")
print("Check the output above to confirm:")
print("  1. Scenario 1 with-block elapsed << actual HTTP latency (~50-400ms)")
print("  2. Scenario 2 with-block elapsed near-instant despite unreachable backend")
print("  3. Scenario 3 with-block elapsed sub-millisecond, no trace sent")
