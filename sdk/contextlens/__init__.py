from contextlens.context import TraceContext
from contextlens.stats import get_stats


def trace(query: str) -> TraceContext:
    """Instrument one RAG query for attribution and faithfulness analysis.

    Returns a context manager. The trace is sent to ContextLens in a
    background thread when the with block exits — the calling code is
    never blocked.

    Example:
        with contextlens.trace(query=user_query) as trace:
            chunks = retriever.fetch(user_query)
            trace.log_chunks(chunks)
            response = llm.generate(chunks, user_query)
            trace.log_response(response)
    """
    return TraceContext(query)


__all__ = ["trace", "get_stats"]
