"""
In-process delivery stats counter.

Thread-safe, pull-based. A developer calls contextlens.get_stats() to check
how many traces were attempted, delivered, and failed in this process.

Scoping decisions:
  - Process-local: resets on restart. Not persistent, not shared across processes.
  - Pull-based: the developer calls get_stats() when they want to know; there is
    no callback or notification. This preserves the fire-and-forget guarantee —
    nothing about sending a trace changes; this counter just increments alongside.
  - Intended use: spot-checking at the end of a batch script or a development
    session. Not intended for production monitoring (use an APM tool for that).
  - 'attempted' increments before the HTTP call is made.
  - 'delivered' increments on any HTTP response from the backend (including 4xx/5xx —
    the trace was received, even if rejected. The backend's 202 means accepted).
  - 'failed' increments when the HTTP call raises an exception (network error,
    timeout, connection refused).
"""

import threading

_lock = threading.Lock()
_attempted: int = 0
_delivered: int = 0
_failed: int = 0


def _record_attempt() -> None:
    global _attempted
    with _lock:
        _attempted += 1


def _record_result(success: bool) -> None:
    global _delivered, _failed
    with _lock:
        if success:
            _delivered += 1
        else:
            _failed += 1


def get_stats() -> dict:
    """Return a snapshot of delivery counters for this process.

    Returns:
        dict with keys:
          attempted — number of traces where a background send was started
          delivered — number of sends that received any HTTP response
          failed    — number of sends that raised a network/timeout exception
    """
    with _lock:
        return {
            "attempted": _attempted,
            "delivered": _delivered,
            "failed": _failed,
        }


def _reset_for_testing() -> None:
    """Reset all counters. Called between test scenarios only."""
    global _attempted, _delivered, _failed
    with _lock:
        _attempted = 0
        _delivered = 0
        _failed = 0
