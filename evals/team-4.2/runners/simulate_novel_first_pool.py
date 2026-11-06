"""Compare pool coverage after deduplicating BEFORE child top-10, offline only.

Consumes previously validated raw-top40 branch traces. No embedding, retriever,
reranker or LLM call. Does not change the production pipeline or report top-5 scores.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import statistics

from rag.eval.metrics import load_questions
from rag.retrieve.fusion import rrf
from rag.retrieve.merge import article_key, take_articles
from rag.retrieve.rerank import DEFAULT_JEV_MODEL, JEV_INSTRUCTIONS, JevReranker, ScoreCache
from rag.schema import Chunk, Hit


def no_network(*args, **kwargs):
    raise RuntimeError("Pool simulation is offline; network is forbidden")


def hits(ids: list[str], raw_ids: list[str] | None = None) -> list[Hit]:
    ranks = {cid: rank for rank, cid in enumerate(raw_ids or ids, 1)}
    return [Hit(cid, 0., ranks[cid], "dense") for cid in ids]


def select_pool(branches: list[dict], chunks: dict[str, Chunk], novel_first: bool) -> list[str]:
    original = hits(branches[0]["article_pool20"], branches[0]["raw_top40"])
    if len(branches) == 1:
        return [h.chunk_id for h in original]
    original_keys = {article_key(chunks[h.chunk_id]) for h in original}
    ranked = {"0": original}
    for branch in branches[1:]:
        raw = hits(branch["raw_top40"])
        if novel_first:
            # Bypass the intermediate 20-article cut in children: first remove
            # original articles from ALL raw top40 hits, then keep 10 new articles.
            novel = [h for h in raw if article_key(chunks[h.chunk_id]) not in original_keys]
            ranked[str(branch["branch"])] = take_articles(novel, chunks, 10)
        else:
            ranked[str(branch["branch"])] = hits(branch["selected"], branch["raw_top40"])
    fused = rrf(ranked, k=60)
    novel = [h for h in fused if article_key(chunks[h.chunk_id]) not in original_keys]
    extra = take_articles(novel, chunks, min(10, max(0, 30 - len(original_keys))))
    return [h.chunk_id for h in [*original, *extra]]


def main() -> None:
    socket.create_connection = no_network
    socket.socket.connect = no_network
    socket.socket.connect_ex = no_network
    root = Path("evals/team-4.2/results")
    audit_dir = root / "decomposition-pool-audit"
    run = root / "doi-thuong-64q-decomposition-anchor20-add10-jev-partial"
    validated = json.loads((audit_dir / "audit.json").read_text(encoding="utf-8"))
    assert validated["replay_exact_questions"] == 64 and validated["api_calls"] == 0
    assert validated["input_metadata_sha256"] == hashlib.sha256((run / "config.json").read_bytes()).hexdigest()
    groups = {}
    for branch in json.loads((audit_dir / "branches.json").read_text(encoding="utf-8")):
        groups.setdefault(branch["question_id"], []).append(branch)
    traces = {t["id"]: t for t in json.loads((run / "query_traces.json").read_text(encoding="utf-8"))}
    questions = {q.id: q for q in load_questions("evals/team-4.2/datasets/benchmark_doi_thuong.jsonl")}
    metadata = json.loads((run / "config.json").read_text(encoding="utf-8"))
    data = Path(metadata["data_dir"])
    chunks = {c.chunk_id: c for c in (
        Chunk.from_dict(json.loads(s)) for s in (data / "processed/chunks.jsonl").read_text(encoding="utf-8").splitlines() if s.strip())}
    cache = sqlite3.connect((data / "cache/rerank.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    records = []
    new_pair_count = 0
    for qid, question in questions.items():
        branches = groups[qid]
        before = select_pool(branches, chunks, novel_first=False)
        assert before == traces[qid]["candidates"], f"Current pool replay failed: {qid}"
        after = select_pool(branches, chunks, novel_first=True)
        original = branches[0]["article_pool20"]
        original_keys = {article_key(chunks[cid]) for cid in original}
        after_keys = {article_key(chunks[cid]) for cid in after}
        assert after[:len(original)] == original and len(after) == len(set(after))
        assert len(after_keys) <= 30 and len(after_keys - original_keys) <= 10
        old_gold = [i for i, g in enumerate(question.gold) if any(g.matches(chunks[cid]) for cid in before)]
        new_gold = [i for i, g in enumerate(question.gold) if any(g.matches(chunks[cid]) for cid in after)]
        added, removed = sorted(set(after) - set(before)), sorted(set(before) - set(after))
        missing_scores = []
        for cid in added:
            key = ScoreCache.key(DEFAULT_JEV_MODEL, question.question, chunks[cid],
                                 instructions=JEV_INSTRUCTIONS, state=JevReranker.build_state(question.question, chunks[cid]))
            if cache.execute("SELECT 1 FROM rerank_scores WHERE key=?", (key,)).fetchone() is None:
                missing_scores.append(cid)
        new_pair_count += len(missing_scores)
        def refs(indices):
            return [{"source": question.gold[i].source, "section": question.gold[i].section} for i in indices]

        records.append({"id": qid, "type": question.type, "question": question.question,
                        "queries": traces[qid]["queries"], "original_articles": len(original_keys),
                        "old_pool_articles": len({article_key(chunks[cid]) for cid in before}),
                        "new_pool_articles": len(after_keys), "new_pool_novel_articles": len(after_keys - original_keys),
                        "old_pool_recall": len(old_gold) / len(question.gold),
                        "new_pool_recall": len(new_gold) / len(question.gold),
                        "gained_gold": refs(sorted(set(new_gold) - set(old_gold))),
                        "lost_gold": refs(sorted(set(old_gold) - set(new_gold))),
                        "added_chunks": added, "removed_chunks": removed,
                        "new_score_cache_misses": missing_scores, "proposed_candidates": after})
    report = {
        "api_calls": 0, "benchmark_rerun": False, "pipeline_modified": False,
        "current_pool_replay_exact": 64, "original_pools_preserved": 64,
        "pool_changed_questions": [r["id"] for r in records if r["added_chunks"] or r["removed_chunks"]],
        "gold_improved_questions": [r["id"] for r in records if r["gained_gold"]],
        "gold_worse_questions": [r["id"] for r in records if r["lost_gold"]],
        "old_mean_pool_recall": statistics.mean(r["old_pool_recall"] for r in records),
        "new_mean_pool_recall": statistics.mean(r["new_pool_recall"] for r in records),
        "new_pair_scores_needed_if_reranked": new_pair_count,
        "old_total_candidate_chunks": sum(len(traces[r["id"]]["candidates"]) for r in records),
        "new_total_candidate_chunks": sum(len(r["proposed_candidates"]) for r in records),
        "max_total_articles": max(r["new_pool_articles"] for r in records),
        "max_novel_articles": max(r["new_pool_novel_articles"] for r in records),
        "rank_policy": "Preserve original Dense ranks in RRF; only change filtering/candidate eligibility",
        "note": "Pool coverage only. No new Recall@5, MRR@5 or answer-quality measurement.",
        "questions": records,
    }
    out = root / "novel-first-pool-simulation"
    out.mkdir(parents=True, exist_ok=True)
    (out / "simulation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Mô phỏng lọc trùng trước top 10 — offline", "",
             "Không sửa pipeline, không gọi API/model và không chạy lại benchmark. Gold chỉ dùng để đánh giá pool sau khi chọn; không dùng để chọn ứng viên.", "",
             "## Chính sách được mô phỏng", "",
             "Giữ nguyên pool gốc tối đa 20 Điều. Mỗi câu con xét toàn bộ raw top 40 chunk đã cache, bỏ Điều đã có trong pool gốc trước, rồi giữ tối đa 10 Điều mới. RRF chọn tổng tối đa 10 Điều bổ sung. Bỏ cap trung gian 20 Điều ở nhánh con; giữ rank Dense ban đầu khi tính RRF để không thay cả cách fusion.", "",
             "## Kết quả", "", "| Kiểm tra | Giá trị |", "|---|---:|"]
    for label, value in (("Replay pool hiện tại khớp trace", "64/64"), ("Pool gốc được giữ nguyên", "64/64"),
                         ("Câu đổi pool", len(report["pool_changed_questions"])),
                         ("Câu có thêm gold", len(report["gold_improved_questions"])),
                         ("Câu mất gold", len(report["gold_worse_questions"])),
                         ("Pool recall trung bình cũ", f'{report["old_mean_pool_recall"]:.6f}'),
                         ("Pool recall trung bình mới", f'{report["new_mean_pool_recall"]:.6f}'),
                         ("Tổng số chunk ứng viên cũ", report["old_total_candidate_chunks"]),
                         ("Tổng số chunk ứng viên mới", report["new_total_candidate_chunks"]),
                         ("Cặp Jev chưa có cache nếu muốn chấm tiếp", new_pair_count),
                         ("Số Điều tối đa", report["max_total_articles"]),
                         ("Số Điều mới tối đa", report["max_novel_articles"])):
        lines.append(f"| {label} | {value} |")
    lines += ["", "## Từng câu có thay đổi pool", "",
              "| ID | Số Điều cũ → mới | Pool recall cũ → mới | Thêm gold | Mất gold |", "|---|---:|---:|---|---|"]
    for r in records:
        if r["id"] not in report["pool_changed_questions"]:
            continue
        def titles(refs):
            return "; ".join(ref["source"] + ": " + str(ref["section"]).split(" > ")[-1] for ref in refs) or "—"
        lines.append(f'| {r["id"]} | {r["old_pool_articles"]} → {r["new_pool_articles"]} | '
                     f'{r["old_pool_recall"]:.3f} → {r["new_pool_recall"]:.3f} | {titles(r["gained_gold"])} | {titles(r["lost_gold"])} |')
    lines += ["", "## Giới hạn", "",
              "Đây là mô phỏng độ phủ pool, không phải benchmark rerank. Thêm gold vào pool không bảo đảm gold vào top 5; thêm ứng viên ngoài gold có thể làm xếp hạng tốt hoặc xấu hơn. Số Điều không tăng quá 30 nhưng số chunk/cặp Jev thực có thể tăng. Không thể suy ra chi phí tiền hoặc độ đúng câu trả lời từ mô phỏng này.",
              "Các câu không được decomposition tách giữ nguyên pool, nên cách này không sửa được các gold đang nằm sâu trong nhánh câu gốc của chúng."]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "questions"}, ensure_ascii=False, indent=2))
    for r in records:
        if r["gained_gold"] or r["lost_gold"]:
            print(r["id"], "gained:", r["gained_gold"], "lost:", r["lost_gold"])


if __name__ == "__main__":
    main()
