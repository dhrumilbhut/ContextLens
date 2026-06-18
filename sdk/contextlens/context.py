import threading
import time
from typing import Any

from contextlens.client import send_trace
from contextlens.config import get_config, warn_missing_key_once
from contextlens.normalizers import normalize_chunks


class TraceContext:
    """Context manager that instruments one RAG query.

    Usage:
        with contextlens.trace(query="...") as trace:
            chunks = retriever.fetch(query)
            trace.log_chunks(chunks)
            response = llm.generate(chunks, query)
            trace.log_response(response)
        # trace is sent in the background here — does not block this line
    """

    def __init__(self, query: str, latency_ms: int | None = None) -> None:
        self.query = query
        self.latency_ms = latency_ms
        self.chunks: list[dict] = []
        self.response: str | None = None
        self._enter_time: float = 0.0

    def log_chunks(self, chunks: list) -> None:
        self.chunks = normalize_chunks(chunks)

    def log_response(self, response: str) -> None:
        self.response = response

    def __enter__(self) -> "TraceContext":
        self._enter_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        cfg = get_config()

        # No-op cases — all return immediately without starting a thread
        if not cfg.enabled:
            return False

        if not cfg.api_key:
            warn_missing_key_once()
            return False

        if exc_type is not None:
            # Exception inside the with block — don't send an incomplete trace
            return False

        if self.response is None:
            # log_response() was never called — nothing to send
            return False

        # Auto-compute latency from context manager duration if not provided
        latency_ms = self.latency_ms
        if latency_ms is None:
            elapsed_s = time.perf_counter() - self._enter_time
            latency_ms = int(elapsed_s * 1000)

        payload = {
            "query": self.query,
            "chunks": self.chunks,
            "response": self.response,
            "latency_ms": latency_ms,
        }

        # Fire and forget — daemon=True so this thread never blocks process shutdown
        threading.Thread(
            target=send_trace,
            args=(payload, cfg.api_url, cfg.api_key, cfg.timeout),
            daemon=True,
        ).start()

        # Never suppress exceptions raised inside the caller's with block
        return False
