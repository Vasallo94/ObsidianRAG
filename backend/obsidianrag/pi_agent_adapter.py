#!/usr/bin/env python3
"""Pi CLI adapter for the ObsidianRAG external-agent JSON protocol."""

import json
import os
import re
import subprocess
import sys


def main() -> None:
    request = json.load(sys.stdin)
    task = request.get("task")
    cases = request.get("cases")
    if task not in {"generate", "judge"} or not isinstance(cases, list):
        raise SystemExit("Invalid external-agent request")

    if task == "generate":
        instruction = (
            "You are the answer stage of a grounded RAG system. Answer every question only "
            "from its contexts. If context is insufficient, say so. Cite source paths exactly. "
            'Return strict JSON only as {"answers":[{"id":str,"answer":str,'
            '"citations":[str]}]}.'
        )
    else:
        instruction = (
            "You are a strict RAG evaluator. Compare each candidate with the private ground "
            "truth and evidence. Return one 0/1 fact score per required fact. Score correctness, "
            "faithfulness, and answer relevance from 0.0 to 1.0. Penalize fluent unsupported "
            'claims. Return strict JSON only as {"judgments":[{"id":str,'
            '"fact_scores":[0],"correctness":number,"faithfulness":number,'
            '"answer_relevance":number,"reason":str}]}.'
        )

    command = [
        "pi",
        "--model",
        os.environ.get("OBSIDIANRAG_PI_MODEL", "openai-codex/gpt-5.6-luna"),
        "--thinking",
        os.environ.get("OBSIDIANRAG_PI_THINKING", "low"),
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-context-files",
        "--no-session",
        "-p",
    ]
    environment = {**os.environ, "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0"}
    result = subprocess.run(
        command,
        input=f"{instruction}\nCASES:\n{json.dumps(cases, ensure_ascii=False)}",
        text=True,
        capture_output=True,
        timeout=int(os.environ.get("OBSIDIANRAG_PI_TIMEOUT", "300")),
        env=environment,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    output = result.stdout.strip()
    if output.startswith("```"):
        output = re.sub(r"^```(?:json)?\s*|\s*```$", "", output, flags=re.DOTALL)
    parsed = json.loads(output)
    json.dump(parsed, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
