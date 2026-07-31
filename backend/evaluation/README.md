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

The evaluator reports source-level Precision@k, Recall@k, hit rate, MRR, MAP@k, nDCG@k, deterministic 95% bootstrap confidence intervals, and mean/p50/p95 latency. Cases may include graded relevance:

```json
{
  "question": "Which document defines the deployment policy?",
  "expected_sources": ["Primary.md", "Related.md"],
  "relevance_grades": [
    {"source": "Primary.md", "grade": 3},
    {"source": "Related.md", "grade": 1}
  ]
}
```

Sources without an explicit grade use binary relevance 1.
