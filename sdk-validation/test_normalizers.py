"""
Phase B validation: chunk format normalizers.

No backend required. No Docker needed. Runs standalone.

Two test tiers:
  Tier 1 — fake stand-in objects that mirror LangChain/LlamaIndex attribute
            shapes without installing either library. Proves the SDK's
            duck-typing detection works and has no hard framework dependency.
  Tier 2 — real langchain-core and llama-index-core objects (skipped
            automatically if those packages are not installed).

Run:
  pip install -e ./sdk
  python sdk-validation/test_normalizers.py
"""

import sys
import traceback

from contextlens.normalizers import normalize_chunks
from contextlens.exceptions import ContextLensError

PASS = "PASS"
FAIL = "FAIL"
_results: list[tuple[str, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    _results.append((name, status))
    marker = "  [PASS]" if condition else "  [FAIL]"
    suffix = f" — {detail}" if detail else ""
    print(f"{marker}  {name}{suffix}")


def assert_chunk(normalized: dict, content: str, source, chunk_index, retriever_score) -> bool:
    return (
        normalized["content"] == content
        and normalized["source"] == source
        and normalized["chunk_index"] == chunk_index
        and normalized["retriever_score"] == retriever_score
    )


# ---------------------------------------------------------------------------
# Fake stand-ins — mirror LangChain/LlamaIndex attribute shapes exactly
# ---------------------------------------------------------------------------

class FakeLangChainDocument:
    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


class FakeLlamaIndexNode:
    def __init__(self, text: str, metadata: dict):
        self._text = text
        self.metadata = metadata

    def get_content(self) -> str:
        return self._text


class FakeNodeWithScore:
    def __init__(self, node, score):
        self.node = node
        self.score = score


# ---------------------------------------------------------------------------
# Tier 1 — fake objects
# ---------------------------------------------------------------------------

print("\n=== Tier 1: fake stand-in objects (no framework install required) ===\n")

# 1. list[str] — regression check on Phase A behavior
result = normalize_chunks(["hello world", "second chunk"])
check(
    "1. list[str] — regression",
    len(result) == 2
    and result[0]["content"] == "hello world"
    and result[0]["source"] is None
    and result[0]["chunk_index"] == 0
    and result[1]["content"] == "second chunk"
    and result[1]["chunk_index"] == 1,
)

# 2. list[dict] — regression check on Phase A behavior
result = normalize_chunks([
    {"content": "refund policy text", "source": "policy.pdf", "chunk_index": 3, "score": 0.91},
    {"content": "terms text", "source": "terms.pdf", "retriever_score": 0.75},
])
check(
    "2. list[dict] — regression (score and retriever_score aliases)",
    result[0]["source"] == "policy.pdf"
    and result[0]["chunk_index"] == 3
    and result[0]["retriever_score"] == 0.91
    and result[1]["retriever_score"] == 0.75,
)

# 3. LangChain Document — full metadata
doc = FakeLangChainDocument(
    page_content="Customers may request a full refund within 30 days.",
    metadata={"source": "refund-policy.pdf", "page": 2, "score": 0.88},
)
result = normalize_chunks([doc])
check(
    "3. LangChain Document — full metadata",
    assert_chunk(result[0],
        content="Customers may request a full refund within 30 days.",
        source="refund-policy.pdf",
        chunk_index=2,    # "page" used as fallback
        retriever_score=0.88,
    ),
)

# 4. LangChain Document — empty metadata (no crash, all optional fields None)
doc_empty = FakeLangChainDocument(
    page_content="Some content with no metadata.",
    metadata={},
)
result = normalize_chunks([doc_empty])
check(
    "4. LangChain Document — empty metadata (no crash, fields None)",
    result[0]["content"] == "Some content with no metadata."
    and result[0]["source"] is None
    and result[0]["chunk_index"] is None
    and result[0]["retriever_score"] is None,
)

# 5. LlamaIndex NodeWithScore — file_name in metadata
node = FakeLlamaIndexNode(
    text="Subscription cancellations require 7 days notice.",
    metadata={"file_name": "terms-of-service.pdf", "chunk_index": 5},
)
nws = FakeNodeWithScore(node=node, score=0.93)
result = normalize_chunks([nws])
check(
    "5. LlamaIndex NodeWithScore — file_name metadata, score present",
    assert_chunk(result[0],
        content="Subscription cancellations require 7 days notice.",
        source="terms-of-service.pdf",
        chunk_index=5,
        retriever_score=0.93,
    ),
)

# 6. LlamaIndex NodeWithScore — score=None (no crash)
node_no_score = FakeLlamaIndexNode(
    text="No score attached to this node.",
    metadata={"file_name": "faq.pdf"},
)
nws_no_score = FakeNodeWithScore(node=node_no_score, score=None)
result = normalize_chunks([nws_no_score])
check(
    "6. LlamaIndex NodeWithScore — score=None (no crash, retriever_score is None)",
    result[0]["retriever_score"] is None
    and result[0]["content"] == "No score attached to this node.",
)

# 7. Unrecognized type — ContextLensError raised with clear message
raised = False
message = ""
try:
    normalize_chunks([42])
except ContextLensError as e:
    raised = True
    message = str(e)
except Exception as e:
    message = f"Wrong exception type: {type(e).__name__}: {e}"
check(
    "7. Unrecognized type — ContextLensError raised",
    raised and "int" in message,
    detail=f'message: "{message}"' if raised else f"ERROR: {message}",
)

# 8. Empty list — no crash, returns []
result = normalize_chunks([])
check("8. Empty list — returns empty list", result == [])


# ---------------------------------------------------------------------------
# Tier 2 — real framework objects (skipped if not installed)
# ---------------------------------------------------------------------------

print("\n=== Tier 2: real langchain-core / llama-index-core objects ===\n")

# LangChain
try:
    from langchain_core.documents import Document as LangChainDoc  # type: ignore

    lc_doc = LangChainDoc(
        page_content="Real LangChain document content.",
        metadata={"source": "real-langchain.pdf", "page": 1},
    )
    result = normalize_chunks([lc_doc])
    check(
        "T2-1. Real LangChain Document — source and page extracted",
        result[0]["content"] == "Real LangChain document content."
        and result[0]["source"] == "real-langchain.pdf"
        and result[0]["chunk_index"] == 1,
    )

    lc_doc_empty = LangChainDoc(page_content="Minimal.", metadata={})
    result = normalize_chunks([lc_doc_empty])
    check(
        "T2-2. Real LangChain Document — empty metadata (no crash)",
        result[0]["source"] is None and result[0]["chunk_index"] is None,
    )

except ImportError:
    print("  [SKIP]  langchain-core not installed — run `pip install langchain-core` to enable")

# LlamaIndex
try:
    from llama_index.core.schema import TextNode, NodeWithScore  # type: ignore

    real_node = TextNode(
        text="Real LlamaIndex node content.",
        metadata={"file_name": "real-llamaindex.pdf"},
    )
    real_nws = NodeWithScore(node=real_node, score=0.77)
    result = normalize_chunks([real_nws])
    check(
        "T2-3. Real LlamaIndex NodeWithScore — file_name and score extracted",
        result[0]["content"] == "Real LlamaIndex node content."
        and result[0]["source"] == "real-llamaindex.pdf"
        and result[0]["retriever_score"] == 0.77,
    )

    real_nws_none = NodeWithScore(node=real_node, score=None)
    result = normalize_chunks([real_nws_none])
    check(
        "T2-4. Real LlamaIndex NodeWithScore — score=None (no crash)",
        result[0]["retriever_score"] is None,
    )

except ImportError:
    print("  [SKIP]  llama-index-core not installed — run `pip install llama-index-core` to enable")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
total = len(_results)
passed = sum(1 for _, s in _results if s == PASS)
failed = total - passed

print(f"{'=' * 50}")
print(f"  Results: {passed}/{total} passed", end="")
if failed:
    print(f"  ({failed} FAILED)")
    for name, status in _results:
        if status == FAIL:
            print(f"    FAILED: {name}")
else:
    print()
print(f"{'=' * 50}")

sys.exit(0 if failed == 0 else 1)
