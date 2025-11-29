"""
Command-line interface for ObsidianRAG.

Available commands:
    obsidianrag serve   - Start the API server
    obsidianrag index   - Index or reindex the vault
    obsidianrag status  - Check system status
    obsidianrag ask     - Ask a question from the command line
"""

from obsidianrag.cli.main import app as cli_app

__all__ = ["cli_app"]
