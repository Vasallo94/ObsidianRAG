"""Command-line interface for ObsidianRAG"""

from pathlib import Path
from typing import Literal, Optional, cast

import typer
from obsidianrag.core.llm_provider import normalize_llm_provider
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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

        response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if response.status_code == 200:
            models = [m["name"] for m in response.json().get("models", [])]
            table.add_row("Ollama", "OK", f"{len(models)} models available")
        else:
            table.add_row("Ollama", "WARN", "Running but error getting models")
    except Exception:
        table.add_row("Ollama", "ERR", "Not running. Run: ollama serve")

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
