"""Command-line interface for ObsidianRAG"""

from pathlib import Path
from typing import Literal, Optional, cast

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from obsidianrag.core.llm_provider import normalize_llm_provider

app = typer.Typer(
    name="obsidianrag",
    help="ObsidianRAG - Query your Obsidian notes with AI",
    add_completion=False,
)

console = Console()


def get_vault_path(vault: Optional[str] = None) -> str:
    """Get vault path from argument or environment."""
    import os

    if vault:
        return vault

    # Try environment variable
    env_path = os.environ.get("OBSIDIAN_PATH")
    if env_path:
        return env_path

    # Try current directory
    if Path(".obsidian").exists():
        return str(Path.cwd())

    console.print("[red]Error: No vault path specified.[/red]")
    console.print("Use --vault or set OBSIDIAN_PATH environment variable.")
    raise typer.Exit(1)


@app.command()
def serve(
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="LLM runtime provider: ollama, lmstudio, or custom",
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="LLM model to use (e.g., gemma3, llama3.2)"
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        help="Base URL for the selected provider (Ollama or compatible chat server)",
    ),
    api_format: Optional[str] = typer.Option(
        None,
        "--api-format",
        help="API format for custom providers: ollama or chat-completions",
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API key for custom compatible providers when required",
    ),
    reranker: Optional[bool] = typer.Option(
        None, "--reranker/--no-reranker", help="Enable/disable reranker"
    ),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload"),
):
    """Start the ObsidianRAG API server."""
    vault_path = get_vault_path(vault)

    provider_info = f"\nProvider: [yellow]{provider}[/yellow]" if provider else ""
    model_info = f"\nModel: [yellow]{model}[/yellow]" if model else ""
    reranker_info = (
        f"\nReranker: [yellow]{'Enabled' if reranker else 'Disabled'}[/yellow]"
        if reranker is not None
        else ""
    )

    console.print(
        Panel.fit(
            f"[bold cyan]ObsidianRAG Server[/bold cyan]\n\n"
            f"Vault: [green]{vault_path}[/green]\n"
            f"URL: [blue]http://{host}:{port}[/blue]{provider_info}{model_info}{reranker_info}",
            title="Starting Server",
        )
    )

    # Configure settings
    from obsidianrag.config import configure_from_vault, get_settings

    configure_from_vault(vault_path)

    # Override settings if specified via CLI
    settings = get_settings()
    if provider:
        normalized = normalize_llm_provider(provider)
        settings.llm_provider = cast(Literal["ollama", "lmstudio", "custom"], normalized)
        if normalized == "lmstudio":
            settings.llm_api_format = "chat-completions"
    if model:
        settings.llm_model = model
    if api_format:
        settings.llm_api_format = cast(Literal["ollama", "chat-completions"], api_format)
    if base_url:
        if settings.llm_provider == "ollama" or settings.llm_api_format == "ollama":
            settings.ollama_base_url = base_url
        else:
            settings.compatible_base_url = base_url
    if api_key:
        settings.compatible_api_key = api_key
    if reranker is not None:
        settings.use_reranker = reranker

    # Start server
    import uvicorn

    from obsidianrag.api.server import create_app

    server_app = create_app(vault_path)
    uvicorn.run(server_app, host=host, port=port, reload=reload)


@app.command()
def index(
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
    force: bool = typer.Option(False, "--force", "-f", help="Force full rebuild"),
):
    """Index or re-index the Obsidian vault."""
    vault_path = get_vault_path(vault)

    console.print(f"Indexing vault: [green]{vault_path}[/green]")

    if force:
        console.print("[yellow]Force rebuild enabled - this may take a while...[/yellow]")

    from obsidianrag.config import configure_from_vault
    from obsidianrag.core.db_service import load_or_create_db

    configure_from_vault(vault_path)

    with console.status("[bold green]Indexing..."):
        db = load_or_create_db(vault_path, force_rebuild=force)

    if db:
        # Get stats
        db_data = db.get()
        total_chunks = len(db_data.get("documents", []))
        sources = set(m.get("source", "") for m in db_data.get("metadatas", []))

        console.print(
            Panel.fit(
                f"[bold green]Indexing complete![/bold green]\n\n"
                f"Notes: {len(sources)}\n"
                f"Chunks: {total_chunks}",
                title="Success",
            )
        )
    else:
        console.print("[red]Indexing failed. Check logs for details.[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
):
    """Check system status and configuration."""
    import os

    table = Table(title="ObsidianRAG Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details")

    # Check vault
    vault_path = get_vault_path(vault) if vault else os.environ.get("OBSIDIAN_PATH", "Not set")
    vault_exists = Path(vault_path).exists() if vault_path and vault_path != "Not set" else False
    table.add_row("Vault", "OK" if vault_exists else "ERR", vault_path)

    # Check Ollama
    try:
        import httpx

        from obsidianrag.config import get_settings as _get_settings

        _settings = _get_settings()
        ollama_url = _settings.ollama_base_url
        response = httpx.get(f"{ollama_url}/api/tags", timeout=2.0)
        if response.status_code == 200:
            models = [m["name"] for m in response.json().get("models", [])]
            table.add_row("Ollama", "OK", f"{len(models)} models available")
        else:
            table.add_row("Ollama", "WARN", "Running but error getting models")
    except Exception as e:
        table.add_row("Ollama", "ERR", f"Not reachable: {e}")

    # Check database
    if vault_exists:
        db_path = Path(vault_path) / ".obsidianrag" / "db"
        if db_path.exists():
            table.add_row("Database", "OK", str(db_path))
        else:
            table.add_row("Database", "WARN", "Not indexed. Run: obsidianrag index")

    console.print(table)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask"),
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
):
    """Ask a question about your notes (without starting server)."""
    vault_path = get_vault_path(vault)

    console.print(f"[bold]{question}[/bold]\n")

    from obsidianrag import ObsidianRAG

    with console.status("[bold green]Thinking..."):
        rag = ObsidianRAG(vault_path)
        answer, sources = rag.ask(question)

    console.print(Panel(answer, title="Answer", border_style="green"))

    if sources:
        console.print("\n[dim]Sources:[/dim]")
        for i, source in enumerate(sources[:5], 1):
            source_path = source.metadata.get("source", "Unknown")
            console.print(f"  {i}. {Path(source_path).name}")


@app.command("v4-index")
def v4_index(
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
):
    """Build and atomically activate an experimental SQLite + LanceDB index."""
    from obsidianrag.config import configure_from_vault
    from obsidianrag.core.db_service import get_embeddings
    from obsidianrag.v4 import build_index

    vault_path = Path(get_vault_path(vault)).resolve()
    configure_from_vault(str(vault_path))
    try:
        with console.status("[bold green]Building experimental v4 index..."):
            result = build_index(vault_path, get_embeddings())
    except RuntimeError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error

    console.print(
        Panel.fit(
            f"Revision: {result.revision}\nNotes: {result.notes}\nChunks: {result.chunks}",
            title="Experimental v4 index ready",
        )
    )


@app.command("v4-search")
def v4_search(
    query: str = typer.Argument(..., help="Query to retrieve from the experimental index"),
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
    k: int = typer.Option(10, "--k", min=1, help="Chunks to return"),
):
    """Search the active experimental index without calling an LLM."""
    from obsidianrag.config import configure_from_vault
    from obsidianrag.core.db_service import get_embeddings
    from obsidianrag.v4 import ExperimentalRetriever

    vault_path = Path(get_vault_path(vault)).resolve()
    configure_from_vault(str(vault_path))
    try:
        retriever = ExperimentalRetriever(vault_path, get_embeddings())
        try:
            documents = retriever.invoke(query, k=k)
        finally:
            retriever.close()
    except RuntimeError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error

    for rank, document in enumerate(documents, 1):
        source = document.metadata.get("source", "Unknown")
        score = document.metadata.get("score", 0.0)
        console.print(f"{rank}. [cyan]{source}[/cyan] ({score:.6f})")


@app.command()
def evaluate(
    dataset: Path = typer.Argument(..., help="JSON dataset with questions and expected sources"),
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
    k: int = typer.Option(10, "--k", min=1, help="Unique source notes to evaluate"),
    reranker: bool = typer.Option(False, "--reranker", help="Include the v3 reranker"),
    engine: Literal["v3", "v4"] = typer.Option("v3", "--engine", help="Retrieval engine: v3 or v4"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write JSON results"),
):
    """Evaluate retrieval against expected source notes without calling an LLM."""
    from obsidianrag.config import configure_from_vault, get_settings
    from obsidianrag.evaluation import evaluate_retrieval, load_dataset

    if engine == "v4" and reranker:
        raise typer.BadParameter(
            "the experimental v4 engine does not yet rerank", param_hint="--reranker"
        )

    vault_path = Path(get_vault_path(vault)).resolve()
    try:
        cases = load_dataset(dataset)
    except (OSError, ValueError) as error:
        console.print(f"[red]Invalid evaluation dataset: {error}[/red]")
        raise typer.Exit(2) from error

    configure_from_vault(str(vault_path))
    settings = get_settings()

    with console.status(f"[bold green]Evaluating {engine} retrieval..."):
        if engine == "v4":
            from obsidianrag.core.db_service import get_embeddings
            from obsidianrag.v4 import ExperimentalRetriever

            try:
                retriever = ExperimentalRetriever(vault_path, get_embeddings())
                try:
                    result = evaluate_retrieval(retriever.invoke, cases, vault_path, k=k)
                finally:
                    retriever.close()
            except RuntimeError as error:
                console.print(f"[red]{error}[/red]")
                raise typer.Exit(1) from error
        else:
            from obsidianrag.core.db_service import load_or_create_db
            from obsidianrag.core.qa_service import create_retriever_with_reranker

            settings.use_reranker = reranker
            settings.retrieval_k = max(settings.retrieval_k, k)
            settings.bm25_k = max(settings.bm25_k, k)
            if reranker:
                settings.reranker_top_n = max(settings.reranker_top_n, k)
            db = load_or_create_db(str(vault_path))
            if db is None:
                console.print("[red]Could not load the vault index.[/red]")
                raise typer.Exit(1)
            retriever = create_retriever_with_reranker(db)
            result = evaluate_retrieval(retriever.invoke, cases, vault_path, k=k)

    table = Table(title=f"Retrieval Evaluation (k={k})")
    table.add_column("Question")
    table.add_column("Recall", justify="right")
    table.add_column("Reciprocal rank", justify="right")
    table.add_column("Latency", justify="right")
    for case in result.cases:
        table.add_row(
            case.question,
            f"{case.recall:.3f}",
            f"{case.reciprocal_rank:.3f}",
            f"{case.latency_seconds * 1000:.1f} ms",
        )
    console.print(table)
    metrics = (
        (f"Precision@{k}", "precision_at_k", result.precision_at_k),
        (f"Recall@{k}", "recall_at_k", result.recall_at_k),
        (f"Hit rate@{k}", "hit_rate_at_k", result.hit_rate_at_k),
        ("MRR", "mean_reciprocal_rank", result.mean_reciprocal_rank),
        (f"MAP@{k}", "mean_average_precision_at_k", result.mean_average_precision_at_k),
        (f"nDCG@{k}", "ndcg_at_k", result.ndcg_at_k),
    )
    for label, key, value in metrics:
        low, high = result.confidence_intervals_95[key]
        console.print(f"{label}: [bold]{value:.3f}[/bold] (95% CI {low:.3f}–{high:.3f})")
    console.print(f"Mean latency: [bold]{result.mean_latency_seconds * 1000:.1f} ms[/bold]")
    console.print(f"p50 latency: [bold]{result.p50_latency_seconds * 1000:.1f} ms[/bold]")
    console.print(f"p95 latency: [bold]{result.p95_latency_seconds * 1000:.1f} ms[/bold]")

    if output:
        import json

        embedding_model = (
            settings.ollama_embedding_model
            if settings.embedding_provider == "ollama"
            else settings.embedding_model
        )
        payload = {
            "engine": engine,
            "embedding_signature": f"{settings.embedding_provider}:{embedding_model}",
            **result.to_dict(),
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        console.print(f"Results written to {output}")


@app.command("compare-evaluations")
def compare_evaluations(
    baseline: Path = typer.Argument(..., help="Baseline evaluation result JSON"),
    candidate: Path = typer.Argument(..., help="Candidate evaluation result JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write comparison JSON"),
):
    """Compare two result files using paired bootstrap confidence intervals."""
    import json

    from obsidianrag.evaluation import compare_evaluation_results

    try:
        result = compare_evaluation_results(
            json.loads(baseline.read_text(encoding="utf-8")),
            json.loads(candidate.read_text(encoding="utf-8")),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error

    table = Table(
        title=f"{result['candidate_engine']} − {result['baseline_engine']} "
        f"({result['case_count']} paired queries)"
    )
    table.add_column("Metric")
    table.add_column("Baseline", justify="right")
    table.add_column("Candidate", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("95% CI", justify="right")
    table.add_column("Better / worse", justify="right")
    for name, metric in result["metrics"].items():
        low, high = metric["confidence_interval_95"]
        table.add_row(
            name,
            f"{metric['baseline']:.3f}",
            f"{metric['candidate']:.3f}",
            f"{metric['delta']:+.3f}",
            f"{low:+.3f}–{high:+.3f}",
            f"{metric['improved_queries']} / {metric['regressed_queries']}",
        )
    console.print(table)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        console.print(f"Results written to {output}")


@app.command()
def version():
    """Show version information."""
    from obsidianrag import __version__

    console.print(
        Panel.fit(
            f"[bold cyan]ObsidianRAG[/bold cyan] v{__version__}\n\n"
            "RAG system for Obsidian notes using LangGraph and Ollama",
            title="Version",
        )
    )


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
