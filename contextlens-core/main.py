"""
ContextLens Core — CLI entry point.

Usage:
    python main.py --demo                   Run the hardcoded demo
    python main.py --input trace.json       Run against your own pipeline output

Input JSON format:
    {
        "query": "...",
        "llm_response": "...",
        "chunks": [
            {"id": "...", "source": "filename.pdf", "text": "..."},
            ...
        ]
    }
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from contextlens.pipeline import run_pipeline
from contextlens.formatter import print_results


def run_demo() -> None:
    import demo as _demo_module  # noqa: F401 — importing for side effects
    # demo.py runs on import when __name__ != "__main__", so we call it directly
    from demo import QUERY, CHUNKS, LLM_RESPONSE
    results = run_pipeline(query=QUERY, chunks=CHUNKS, llm_response=LLM_RESPONSE)
    print_results(query=QUERY, chunks=CHUNKS, results=results)


def run_from_file(path: Path) -> None:
    with open(path) as f:
        data = json.load(f)
    query = data["query"]
    chunks = data["chunks"]
    llm_response = data["llm_response"]
    results = run_pipeline(query=query, chunks=chunks, llm_response=llm_response)
    print_results(query=query, chunks=chunks, results=results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ContextLens Core — RAG hallucination debugger"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true", help="Run the hardcoded demo")
    group.add_argument("--input", metavar="FILE", help="Path to a trace JSON file")
    args = parser.parse_args()

    if args.demo:
        from demo import QUERY, CHUNKS, LLM_RESPONSE
        results = run_pipeline(query=QUERY, chunks=CHUNKS, llm_response=LLM_RESPONSE)
        print_results(query=QUERY, chunks=CHUNKS, results=results)
    else:
        path = Path(args.input)
        if not path.exists():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        run_from_file(path)


if __name__ == "__main__":
    main()
