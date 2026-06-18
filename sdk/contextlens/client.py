import logging

import httpx

logger = logging.getLogger("contextlens")


def send_trace(payload: dict, api_url: str, api_key: str, timeout: float) -> None:
    """Send a trace payload to the ContextLens ingest endpoint.

    Runs in a daemon background thread. Fails silently — any exception is
    logged at DEBUG level so it stays invisible by default but is inspectable
    when a developer sets logging.getLogger("contextlens").setLevel(logging.DEBUG).

    Choosing DEBUG over total silence is a deliberate trade-off: "fails silently"
    and "fails silently but is debuggable on request" are both safe, and the
    second is strictly better for self-hosted developer tooling where the
    developer owns the process and can inspect logs if something seems wrong.
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            client.post(
                f"{api_url}/ingest",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except Exception:
        logger.debug("ContextLens: failed to send trace", exc_info=True)
