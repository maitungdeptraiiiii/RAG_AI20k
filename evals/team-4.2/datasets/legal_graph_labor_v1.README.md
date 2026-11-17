# Legal Graph — labor benchmark v1

Scope: structural and temporal retrieval for Vietnamese employment contracts.
This benchmark does not use concepts/anchors, Contract Graph, rule engines or LLMs.

`legal_graph_labor_v1.jsonl` has 28 curated cases with independent expected
provisions, document identities, date boundaries, references, guidance scope and
annex content. Expected results must not be regenerated from system output.

Run from the repository root after installing the project's `graph` extra:

```powershell
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
# Set NEO4J_PASSWORD through your local environment; never commit it.
python scripts/team-4.2/eval_legal_graph.py --publish
```

The development instance created for this work uses
`bolt://127.0.0.1:17687` (Neo4j Browser: `http://127.0.0.1:17474`).
Set `NEO4J_URI` accordingly. Credentials stay in the local environment.

Use `--namespace legal-eval` for an isolated graph namespace. `--publish` builds,
validates and publishes into that namespace; omit it to evaluate an already
published build. The evaluator refuses stale builds. `--legal-dir`, `--dataset`,
`--uri` and `--out` can override paths and connection settings.

Without Neo4j:

```powershell
python scripts/team-4.2/eval_legal_graph.py --structural-only
```

Structural-only mode runs integrity checks and reports zero API cases. It is not
equivalent to a successful API benchmark. Reports identify the mode, dataset
checksum, snapshot/build IDs, errors, per-case outcomes, verification statuses,
and p50/p95 query latency. Query latency is a local single-run measurement, not
a concurrent-load benchmark.

An API case passing means its retrieval assertions held. It does not establish
that `needs_review` or `conflicted` legal text is safe for a legal conclusion.
The reference case only asserts a known included target, so it cannot measure
overall reference precision/recall. The original 100-reference manual sample
still requires human labels for a separate legal-quality evaluation.

Related technical tests:

```powershell
Set-Location app/team-4.2
python -m pytest tests/test_legal_graph.py tests/test_legal_graph_hardening.py -q
# Set NEO4J_TEST_URI / NEO4J_TEST_PASSWORD for real Neo4j tests:
python -m pytest tests/test_legal_graph_neo4j.py -q
```
