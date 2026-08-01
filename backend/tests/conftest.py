"""Shared pytest fixtures for ObsidianRAG."""

from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture(name="mock_vault")
def mock_vault_fixt(tmp_path: Path) -> Generator[Path, None, None]:
    """Create a temporary Obsidian vault with representative Markdown notes."""
    vault = tmp_path / "test_vault"
    (vault / ".obsidian").mkdir(parents=True)
    notes = {
        "Python Basics.md": "# Python Basics\n\nVariables store data.\n",
        "Advanced Python.md": "# Advanced Python\n\nDecorators modify behavior.\n",
        "Data Types.md": "# Data Types\n\nLists are ordered collections.\n",
        "subfolder/Nested Note.md": "# Nested Note\n\nNested content.\n",
    }
    for name, content in notes.items():
        path = vault / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    yield vault
