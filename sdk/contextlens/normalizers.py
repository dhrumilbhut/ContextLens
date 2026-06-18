import logging

from contextlens.exceptions import ContextLensError

logger = logging.getLogger("contextlens")


# ---------------------------------------------------------------------------
# Per-type normalizers
# ---------------------------------------------------------------------------

def _normalize_str_chunk(chunk: str, index: int) -> dict:
    return {
        "content": chunk,
        "source": None,
        "chunk_index": index,
        "retriever_score": None,
    }


def _normalize_dict_chunk(chunk: dict, index: int) -> dict:
    return {
        "content": chunk.get("content", ""),
        "source": chunk.get("source"),
        "chunk_index": chunk.get("chunk_index", index),
        # accept both "retriever_score" (API name) and "score" (SDK.md example)
        "retriever_score": chunk.get("retriever_score") or chunk.get("score"),
    }


# ---------------------------------------------------------------------------
# Duck-typing detectors — no import of langchain or llama-index required.
# The SDK itself has zero dependency on either framework.
# ---------------------------------------------------------------------------

def _is_langchain_document(obj) -> bool:
    return hasattr(obj, "page_content") and hasattr(obj, "metadata")


def _is_llamaindex_node_with_score(obj) -> bool:
    return hasattr(obj, "node") and hasattr(obj, "score")


def _normalize_langchain_document(doc, index: int) -> dict:
    metadata = doc.metadata or {}
    return {
        "content": doc.page_content,
        "source": metadata.get("source"),
        # "page" is common for PDF loaders; use as chunk_index fallback
        "chunk_index": metadata.get("chunk_index") or metadata.get("page"),
        # retriever_score is rarely in Document.metadata — default None
        "retriever_score": metadata.get("score"),
    }


def _normalize_llamaindex_node(node_with_score, index: int) -> dict:
    node = node_with_score.node
    # prefer get_content() (stable public API); fall back to .text attribute
    if hasattr(node, "get_content"):
        content = node.get_content()
    else:
        content = getattr(node, "text", "")
    metadata = getattr(node, "metadata", {}) or {}
    return {
        "content": content,
        # LlamaIndex commonly uses "file_name"; fall back to "source"
        "source": metadata.get("file_name") or metadata.get("source"),
        "chunk_index": metadata.get("chunk_index"),
        # score IS reliably present on NodeWithScore — that's the wrapper's purpose
        "retriever_score": node_with_score.score,
    }


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def normalize_chunks(chunks: list) -> list[dict]:
    """Normalize any supported chunk format into the /ingest ChunkInput schema.

    Supported formats:
      1. list[str]
      2. list[dict]  — keys: content, source, chunk_index, retriever_score / score
      3. list of LangChain Document objects (detected by duck-typing)
      4. list of LlamaIndex NodeWithScore objects (detected by duck-typing)

    Check order: str and dict are checked first (cheapest, unambiguous).
    Duck-typed checks follow. An unrecognized type raises ContextLensError
    synchronously — this is intentional. log_chunks() is called by the
    developer inline inside their with block, so a bad type is a programming
    error in their integration code. The synchronous raise gives them an
    immediate, clear error during development. This is distinct from __exit__,
    which must never raise — that guarantee covers network/availability
    failures, not developer integration mistakes.
    """
    if not chunks:
        return []

    normalized = []
    for i, chunk in enumerate(chunks):
        if isinstance(chunk, str):
            normalized.append(_normalize_str_chunk(chunk, i))
        elif isinstance(chunk, dict):
            normalized.append(_normalize_dict_chunk(chunk, i))
        elif _is_langchain_document(chunk):
            normalized.append(_normalize_langchain_document(chunk, i))
        elif _is_llamaindex_node_with_score(chunk):
            normalized.append(_normalize_llamaindex_node(chunk, i))
        else:
            raise ContextLensError(
                f"Unrecognized chunk format at index {i}: {type(chunk).__name__}. "
                f"Expected str, dict, LangChain Document, or LlamaIndex NodeWithScore."
            )

    return normalized
