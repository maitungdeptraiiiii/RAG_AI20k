"""Audit where saved gold evidence drops out of decomposition retrieval, with no API.

Read-only SQLite access; cached HyDE/query vectors only; persisted document vectors
are replayed in memory using the installed Qdrant local cosine implementation.
Network connections are forbidden. This does not call a retriever/model or benchmark runner.
"""

from __future__ import annotations

import argparse
from array import array
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import pickle
import socket
import sqlite3

import numpy as np

from rag.advanced.hyde import HYDE_SYSTEM
from rag.eval.metrics import load_questions
from rag.generate.llm import LLMCache
from rag.index.embedder import EmbeddingCache
from rag.retrieve.fusion import rrf
from rag.retrieve.merge import article_key, merge_by_article, take_articles
from rag.schema import Chunk, Hit


def read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def reject_network(*args, **kwargs):
    raise RuntimeError("Offline audit forbids network access; cache misses must fail")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="evals/team-4.2/results/decomposition-pool-audit")
    args = parser.parse_args()
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    socket.socket.connect_ex = reject_network
    from qdrant_client.local.distances import cosine_similarity

    run = Path("evals/team-4.2/results/doi-thuong-64q-decomposition-anchor20-add10-jev-partial")
    metadata = json.loads((run / "config.json").read_text(encoding="utf-8"))
    data = Path(metadata["data_dir"])
    traces = json.loads((run / "query_traces.json").read_text(encoding="utf-8"))
    questions = {q.id: q for q in load_questions("evals/team-4.2/datasets/benchmark_doi_thuong.jsonl")}
    chunks = {c.chunk_id: c for c in (
        Chunk.from_dict(json.loads(line)) for line in (data / "processed/chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    decomp = metadata["decomposition"]
    raw_limit = metadata["arm_k"] * metadata["article_pool_factor"]
    base_limit = metadata["rerank_n"]
    child_limit = decomp["per_query_k"]

    # Mirror LocalCollection.load_vectors, NOT upsert (which casts/normalizes
    # differently). Read only trusted, locally generated Qdrant snapshot records.
    points, seen = [], set()
    storage_path = data / "indexes/vector/qdrant/collection/chunks/storage.sqlite"
    with read_only(storage_path) as storage:
        for (blob,) in storage.execute("SELECT point FROM points ORDER BY rowid DESC"):
            point = pickle.loads(blob)
            if str(point.id) not in seen:
                seen.add(str(point.id))
                points.append(point)
    ids = [point.payload["chunk_id"] for point in points]
    if len(ids) != len(set(ids)) or set(ids) != set(chunks):
        raise ValueError("Snapshot vector IDs and chunk store do not match")
    vectors = np.array([point.vector for point in points])
    llm = read_only(data / "cache/llm.sqlite")
    embeddings = read_only(data / "cache/embeddings.sqlite")
    branches, audits, replay_mismatches = [], [], []
    query_count = 0

    for trace in traces:
        qid = trace["id"]
        lists, original, branch_records = {}, [], []
        for index, query in enumerate(trace["queries"]):
            messages = [{"role": "system", "content": HYDE_SYSTEM},
                        {"role": "user", "content": f"CÂU HỎI: {query}"}]
            cache_key = LLMCache.key(metadata["llm"], None, messages)
            passage = llm.execute("SELECT text FROM completions WHERE key=?", (cache_key,)).fetchone()
            if not passage:
                raise ValueError(f"Missing cached HyDE: {qid}/q{index}; no API fallback")
            text = query + "\n" + passage[0]
            cache_key = EmbeddingCache.key(metadata["index_signature"]["embed_model"] + "#retrieval.query", text)
            row = embeddings.execute("SELECT vec FROM embeddings WHERE key=?", (cache_key,)).fetchone()
            if not row:
                raise ValueError(f"Missing cached query embedding: {qid}/q{index}; no API fallback")
            vector = np.array(array("f", row[0]).tolist())
            scores = cosine_similarity(vector, vectors)
            order = np.argsort(scores)[::-1]
            all_hits = [Hit(ids[i], float(scores[i]), rank, "dense") for rank, i in enumerate(order, 1)]
            article_positions = {}
            for hit in all_hits:
                article_positions.setdefault(article_key(chunks[hit.chunk_id]), len(article_positions) + 1)
            raw = all_hits[:raw_limit]
            is_original = index == 0 and query == trace["question"] and decomp["include_original"]
            limit = base_limit if is_original else child_limit
            candidates = take_articles(raw, chunks, max(base_limit, limit))
            article_hits = merge_by_article(candidates, chunks)
            selected_ids = {cid for h in article_hits[:limit] for cid in (h.chunk_id, *h.merged)}
            selected = [h for h in candidates if h.chunk_id in selected_ids]
            lists[str(index)] = selected
            if is_original:
                original = candidates
            record = {"question_id": qid, "branch": index, "query": query, "original": is_original,
                      "raw_top40": [h.chunk_id for h in raw],
                      "article_pool20": [h.chunk_id for h in candidates],
                      "selected": [h.chunk_id for h in selected],
                      "gold_best_positions": []}
            for gold in questions[qid].gold:
                matches = [h for h in all_hits if gold.matches(chunks[h.chunk_id])]
                record["gold_best_positions"].append({"source": gold.source, "section": gold.section,
                                                       "best_chunk_rank": matches[0].rank if matches else None,
                                                       "best_article_rank": min(article_positions[article_key(chunks[h.chunk_id])]
                                                                                for h in matches) if matches else None})
            branch_records.append(record)
            query_count += 1

        # Rebuild exactly the recorded pool policy, without accessing gold labels.
        if len(trace["queries"]) == 1:
            final = original
        else:
            fused = rrf(lists, k=metadata["rrf_k"])
            original_keys = {article_key(chunks[h.chunk_id]) for h in original}
            novel = [h for h in fused if article_key(chunks[h.chunk_id]) not in original_keys]
            limit = min(decomp["max_new_articles"], max(0, decomp["pool_size"] - len(original_keys)))
            extra = take_articles(novel, chunks, limit) if limit else []
            final = [replace(h, rank=i) for i, h in enumerate([*original, *extra], 1)]
        final_ids = [h.chunk_id for h in final]
        exact = final_ids == trace["candidates"]
        if not exact:
            replay_mismatches.append(qid)
        raw_union = {cid for branch in branch_records for cid in branch["raw_top40"]}
        article_union = {cid for branch in branch_records for cid in branch["article_pool20"]}
        selected_union = {cid for branch in branch_records for cid in branch["selected"]}
        for gold in questions[qid].gold:
            def found(cids):
                return any(gold.matches(chunks[cid]) for cid in cids)

            if found(trace["top5"]):
                stage = "present_top5"
            elif found(trace["candidates"]):
                stage = "in_final_pool_but_not_top5"
            elif found(selected_union):
                stage = "discarded_at_final_new10_budget"
            elif found(article_union):
                stage = "discarded_at_child_top10"
            elif found(raw_union):
                stage = "discarded_at_branch_article20"
            else:
                stage = "outside_raw_top40_all_existing_branches"
            audits.append({"id": qid, "question": questions[qid].question, "type": questions[qid].type,
                           "source": gold.source, "section": gold.section, "stage": stage,
                           "replay_exact": exact, "query_count": len(branch_records),
                           "best_branch_positions": [b["gold_best_positions"][i]["best_chunk_rank"]
                               for b in branch_records for i, g in enumerate(questions[qid].gold) if g == gold],
                           "best_branch_article_positions": [b["gold_best_positions"][i]["best_article_rank"]
                               for b in branch_records for i, g in enumerate(questions[qid].gold) if g == gold]})
        branches.extend(branch_records)

    if replay_mismatches:
        raise ValueError(f"Pool replay differs for {replay_mismatches}; do not publish causal stage assignments")
    counter = Counter(a["stage"] for a in audits)
    counts = {stage: counter[stage] for stage in (
        "present_top5", "in_final_pool_but_not_top5", "discarded_at_final_new10_budget",
        "discarded_at_child_top10", "discarded_at_branch_article20",
        "outside_raw_top40_all_existing_branches")}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {"api_calls": 0, "network_connections_blocked": True, "benchmark_rerun": False,
              "queries_read_from_cache": query_count, "replay_exact_questions": len(traces),
              "gold_ref_count": len(audits), "stage_counts": counts,
              "method": "Read-only stored vectors/cache; same dtype/order/cosine as local Qdrant; no model calls",
              "input_metadata_sha256": hashlib.sha256((run / "config.json").read_bytes()).hexdigest(),
              "gold_audit": audits}
    (out / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "branches.json").write_text(json.dumps(branches, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "gold_audit"}, ensure_ascii=False, indent=2))
    for item in audits:
        if item["stage"] != "present_top5":
            print(item["id"], item["stage"], item["source"], item["section"], item["best_branch_positions"])


if __name__ == "__main__":
    main()
