# Public Retrieval Evaluation Fixture

This directory contains a small, synthetic Obsidian vault and expected-source questions. It is safe to publish and provides a reproducible smoke benchmark for retrieval changes.

Run the current engine:

```bash
obsidianrag index --vault evaluation/sample-vault --force
obsidianrag evaluate evaluation/questions.json --vault evaluation/sample-vault --k 5
```

Run the experimental v4 engine:

```bash
pip install 'obsidianrag[v4]'
obsidianrag v4-index --vault evaluation/sample-vault
obsidianrag evaluate evaluation/questions.json --vault evaluation/sample-vault --engine v4 --k 5
```

The fixture covers English and Spanish questions, exact technical terms, aliases, headings, wikilinks, and similarly named notes. It is a smoke benchmark, not evidence of production retrieval quality. Larger community-contributed datasets should follow the same schema without including private notes.
