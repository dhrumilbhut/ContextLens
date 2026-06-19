import logging

import httpx

from contextlens.stats import _record_attempt, _record_result

logger = logging.getLogger("contextlens")


def send_trace(payload: dict, api_url: str, api_key: str, timeout: float) -> None:
    """Send a trace payload to the ContextLens ingest endpoint.

    Runs in a daemon background thread. Fails silently — any exception is
    logged at DEBUG level so it stays invisible by default but is inspectable
    when a developer sets logging.getLogger("contextlens").setLevel(logging.DEBUG).

    Stats counters are updated from inside this thread — zero overhead on the
    caller's code path. attempted increments before the HTTP call; delivered/failed
    increment after the result is known.
    """
    _record_attempt()
    try:
        with httpx.Client(timeout=timeout) as client:
            client.post(
                f"{api_url}/ingest",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        _record_result(success=True)
    except Exception:
        _record_result(success=False)
        logger.debug("ContextLens: failed to send trace", exc_info=True)
