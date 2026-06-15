"""
Prints pipeline results to the terminal using rich.
Green = faithful, yellow = partial, red = unfaithful.
"""

from rich.console import Console
from rich.text import Text
from rich.rule import Rule

console = Console(legacy_windows=False)

VERDICT_COLOR = {
    "faithful": "green",
    "partial": "yellow",
    "unfaithful": "red",
}

VERDICT_ICON = {
    "faithful": "✓",
    "partial": "⚠",
    "unfaithful": "✗",
}

VERDICT_LABEL = {
    "faithful": "FAITHFUL",
    "partial": "PARTIAL",
    "unfaithful": "UNFAITHFUL",
}


def _failure_label(result: dict) -> str:
    ft = result.get("failure_type")
    if ft == "retrieval":
        return "Retrieval failure — this claim has no source in the retrieved context"
    if ft == "generation":
        return f"Generation failure — {result['reason']}"
    return result["reason"]


def print_results(query: str, chunks: list[dict], results: list[dict]) -> None:
    console.print()
    console.print(
        Text("ContextLens — RAG Hallucination Debugger", style="bold white"),
    )
    console.print(Rule(style="dim white"))

    source_names = ", ".join(dict.fromkeys(c["source"] for c in chunks))
    console.print(f"[bold]Query:[/bold] {query!r}")
    console.print(
        f"[bold]Retrieved[/bold] {len(chunks)} chunks from: [dim]{source_names}[/dim]"
    )
    console.print(f"[bold]Processing[/bold] {len(results)} claims...")
    console.print(Rule(style="dim white"))

    for i, result in enumerate(results, start=1):
        verdict = result["verdict"]
        color = VERDICT_COLOR[verdict]
        icon = VERDICT_ICON[verdict]
        label = VERDICT_LABEL[verdict]

        console.print(f"\n[bold]Claim {i}:[/bold] {result['claim']!r}\n")

        attribution = result["attribution"]
        chunk = attribution["chunk"]
        attr_score = attribution["score"]
        if chunk:
            console.print(
                f"  [bold]Attribution:[/bold]  [cyan]{chunk['source']}[/cyan]"
                f"  [dim](score: {attr_score:.2f})[/dim]"
            )
        else:
            console.print(
                f"  [bold]Attribution:[/bold]  [dim]none found  (best score: {attr_score:.2f})[/dim]"
            )

        faith_score = result["faithfulness_score"]
        console.print(
            f"  [bold]Faithfulness:[/bold] [{color}]{label}[/{color}]"
            f"  [dim](score: {faith_score:.2f})[/dim]"
        )

        failure_line = _failure_label(result)
        console.print(f"\n  [{color}]{icon}[/{color}] {failure_line}")
        console.print(Rule(style="dim white"))

    # Summary
    total = len(results)
    faithful_count = sum(1 for r in results if r["verdict"] == "faithful")
    partial_count = sum(1 for r in results if r["verdict"] == "partial")
    unfaithful_count = sum(1 for r in results if r["verdict"] == "unfaithful")
    retrieval_failures = sum(1 for r in results if r.get("failure_type") == "retrieval")
    generation_failures = sum(1 for r in results if r.get("failure_type") == "generation")

    def pct(n: int) -> str:
        return f"{round(n / total * 100)}%" if total else "0%"

    console.print()
    console.print(Text("Summary", style="bold white"))
    console.print(Rule(style="dim white"))
    console.print(f"  [bold]Total claims:[/bold]       {total}")
    console.print(f"  [green]Faithful:[/green]          {faithful_count} ({pct(faithful_count)})")
    console.print(f"  [yellow]Partial:[/yellow]           {partial_count} ({pct(partial_count)})")
    console.print(f"  [red]Unfaithful:[/red]        {unfaithful_count} ({pct(unfaithful_count)})")
    console.print()
    console.print(
        f"  [red]Retrieval failures:[/red]   {retrieval_failures}"
        + (" — fix your search or chunking" if retrieval_failures else "")
    )
    console.print(
        f"  [yellow]Generation failures:[/yellow]  {generation_failures}"
        + (" — fix your prompt or model" if generation_failures else "")
    )
    console.print()
