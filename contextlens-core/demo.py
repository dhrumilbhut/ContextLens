"""
ContextLens Core — hardcoded demo. Run this to see the pipeline in action.

    python demo.py

You need OPENAI_API_KEY in your environment or a .env file.
"""

from dotenv import load_dotenv
load_dotenv()

from contextlens.pipeline import run_pipeline
from contextlens.formatter import print_results

QUERY = "What is your refund policy?"

CHUNKS = [
    {
        "id": "chunk_1",
        "source": "refund-policy.pdf",
        "text": (
            "Customers may request a full refund within 30 days of the original purchase date. "
            "To initiate a refund, contact our support team with your order number. "
            "Refunds are returned to the original payment method."
        ),
    },
    {
        "id": "chunk_2",
        "source": "terms-of-service.pdf",
        "text": (
            "Subscription cancellations must be submitted at least 7 business days before the "
            "next billing cycle. Cancellations submitted after this window will take effect in "
            "the following billing period."
        ),
    },
    {
        "id": "chunk_3",
        "source": "refund-policy.pdf",
        "text": (
            "Refunds for physical products include free return shipping within the continental US. "
            "Digital products are non-refundable once the license key has been activated."
        ),
    },
]

# This LLM response has been crafted to demonstrate all three outcomes:
# - Claim 1: faithful to chunk_1
# - Claim 2: partial (drops "business" from "7 business days") -> generation failure
# - Claim 3: pure hallucination with no source in any chunk -> retrieval failure
LLM_RESPONSE = (
    "Our refund policy allows customers to request a full refund within 30 days of purchase. "
    "Subscription cancellations require 7 days notice before the next billing cycle. "
    "Once a refund is approved, funds are typically returned within 2 to 3 business days."
)

if __name__ == "__main__":
    results = run_pipeline(query=QUERY, chunks=CHUNKS, llm_response=LLM_RESPONSE)
    print_results(query=QUERY, chunks=CHUNKS, results=results)
