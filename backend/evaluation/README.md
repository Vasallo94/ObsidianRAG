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
obsidianrag evaluate evaluation/questions.json --vault evaluation/sample-vault --engine v4-fts --k 5
```

The fixture covers English and Spanish questions, exact technical terms, aliases, headings, wikilinks, and similarly named notes. It is a smoke benchmark, not evidence of production retrieval quality. Larger community-contributed datasets should follow the same schema without including private notes.

The evaluator reports source-level Precision@k, Recall@k, hit rate, MRR, MAP@k, nDCG@k, evidence recall, deterministic 95% bootstrap confidence intervals, and mean/p50/p95 latency. Evidence recall checks that the selected chunk contains each declared `supporting_evidence` quote, preventing a correct note with the wrong chunk from counting as fully grounded. Cases may include graded relevance:

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

Saved runs can be compared offline with `obsidianrag compare-evaluations baseline.json candidate.json`. Cases are paired by question, and the command reports metric deltas with paired 95% bootstrap intervals.

`obsidianrag evaluate-agent` sends questions and FTS5-retrieved chunks to the generator, then sends candidate answers, required facts, supporting evidence, citations, and retrieved contexts to the judge. It reports source/evidence recall, required-fact coverage, citation precision/recall, correctness, faithfulness, and answer relevance with confidence intervals. It requires explicit `--allow-private-data` confirmation because external commands may use remote providers. `python -m obsidianrag.pi_agent_adapter` is an optional Pi/Luna adapter for this protocol.
