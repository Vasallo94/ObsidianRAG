"""Command-line interface for ObsidianRAG"""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="obsidianrag",
    help="🧠 ObsidianRAG - Query your Obsidian notes with AI",
    add_completion=False
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
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload")
):
    """Start the ObsidianRAG API server."""
    vault_path = get_vault_path(vault)
    
    console.print(Panel.fit(
        f"🧠 [bold cyan]ObsidianRAG Server[/bold cyan]\n\n"
        f"📁 Vault: [green]{vault_path}[/green]\n"
        f"🌐 URL: [blue]http://{host}:{port}[/blue]",
        title="Starting Server"
    ))
    
    # Configure settings
    from obsidianrag.config import configure_from_vault
    configure_from_vault(vault_path)
    
    # Start server
    import uvicorn

    from obsidianrag.api.server import create_app
    
    server_app = create_app(vault_path)
    uvicorn.run(server_app, host=host, port=port, reload=reload)


@app.command()
def index(
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault"),
    force: bool = typer.Option(False, "--force", "-f", help="Force full rebuild")
):
    """Index or re-index the Obsidian vault."""
    vault_path = get_vault_path(vault)
    
    console.print(f"📚 Indexing vault: [green]{vault_path}[/green]")
    
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
        total_chunks = len(db_data.get('documents', []))
        sources = set(m.get('source', '') for m in db_data.get('metadatas', []))
        
        console.print(Panel.fit(
            f"✅ [bold green]Indexing complete![/bold green]\n\n"
            f"📄 Notes: {len(sources)}\n"
            f"📦 Chunks: {total_chunks}",
            title="Success"
        ))
    else:
        console.print("[red]❌ Indexing failed. Check logs for details.[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault")
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
    table.add_row(
        "Vault",
        "✅" if vault_exists else "❌",
        vault_path
    )
    
    # Check Ollama
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if response.status_code == 200:
            models = [m["name"] for m in response.json().get("models", [])]
            table.add_row("Ollama", "✅", f"{len(models)} models available")
        else:
            table.add_row("Ollama", "⚠️", "Running but error getting models")
    except Exception:
        table.add_row("Ollama", "❌", "Not running. Run: ollama serve")
    
    # Check database
    if vault_exists:
        db_path = Path(vault_path) / ".obsidianrag" / "db"
        if db_path.exists():
            table.add_row("Database", "✅", str(db_path))
        else:
            table.add_row("Database", "⚠️", "Not indexed. Run: obsidianrag index")
    
    console.print(table)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Question to ask"),
    vault: Optional[str] = typer.Option(None, "--vault", "-v", help="Path to Obsidian vault")
):
    """Ask a question about your notes (without starting server)."""
    vault_path = get_vault_path(vault)
    
    console.print(f"❓ [bold]{question}[/bold]\n")
    
    from obsidianrag import ObsidianRAG
    
    with console.status("[bold green]Thinking..."):
        rag = ObsidianRAG(vault_path)
        answer, sources = rag.ask(question)
    
    console.print(Panel(answer, title="Answer", border_style="green"))
    
    if sources:
        console.print("\n[dim]Sources:[/dim]")
        for i, source in enumerate(sources[:5], 1):
            source_path = source.metadata.get('source', 'Unknown')
            console.print(f"  {i}. {Path(source_path).name}")


@app.command()
def version():
    """Show version information."""
    from obsidianrag import __version__
    
    console.print(Panel.fit(
        f"🧠 [bold cyan]ObsidianRAG[/bold cyan] v{__version__}\n\n"
        "RAG system for Obsidian notes using LangGraph and Ollama",
        title="Version"
    ))


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
