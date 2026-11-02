"""Chạy evaluation — TV3 (retrieval cùng TV2; generation/guardrail cùng TV4, TV5).

    retrieval_rows(questions, retriever, configs)  -> mỗi (câu, cấu hình) một dòng: Recall@5, Hit@5,
                                                       MRR@5, Recall@20 (giới hạn trên của rerank)
    answer_rows(questions, pipeline)               -> mỗi câu một dòng: có từ chối không, context có
                                                       chứa gold không, câu trả lời + citation (để chấm tay)
    ragas_rows(questions, pipeline)                -> dữ liệu cho RAGAS (user_input, retrieved_contexts,
                                                       response, reference)
    draft_reference(question, store, llm)          -> đáp án mẫu NHÁP từ text trang gold (người viết
                                                       câu hỏi phải kiểm tra lại)
    summary_markdown(rows)                         -> bảng cấu hình × chỉ số, toàn bộ và theo `type`

Câu out_of_scope không tính vào Recall/MRR (metric trả None) và không đưa vào RAGAS.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from rag.eval.metrics import hit_at_k, mean, mrr_at_k, recall_at_k
from rag.index.store import ChunkStore
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import LLM, Question

# tên cấu hình -> (mode, rerank)
RETRIEVAL_CONFIGS: dict[str, tuple[str, bool]] = {
    "bm25": ("bm25", False),
    "dense": ("dense", False),
    "hybrid": ("hybrid", False),
    "hybrid+rerank": ("hybrid", True),
}

METRICS = ("recall@5", "hit@5", "mrr@5", "recall@20")


def retrieval_rows(
    questions: Sequence[Question],
    retriever: HybridRetriever,
    configs: Sequence[str] = ("bm25", "dense", "hybrid"),
    *,
    k: int = 5,
    pool_k: int = 20,
) -> list[dict[str, Any]]:
    unknown = [c for c in configs if c not in RETRIEVAL_CONFIGS]
    if unknown:
        raise ValueError(f"Cấu hình không hợp lệ: {unknown}; chọn trong {list(RETRIEVAL_CONFIGS)}")
    chunks = retriever.chunks
    rows: list[dict[str, Any]] = []
    for q in questions:
        if not q.in_scope:
            continue
        for name in configs:
            mode, rerank = RETRIEVAL_CONFIGS[name]
            res = retriever.retrieve(q.question, k, mode=mode, rerank=rerank)   # type: ignore[arg-type]
            top = [h.chunk_id for h in res.hits]
            pool = [h.chunk_id for h in res.ranked]
            rows.append({
                "id": q.id,
                "type": q.type,
                "author": q.author,
                "config": name,
                "recall@5": recall_at_k(q, top, chunks, k),
                "hit@5": hit_at_k(q, top, chunks, k),
                "mrr@5": mrr_at_k(q, top, chunks, k),
                "recall@20": recall_at_k(q, pool, chunks, pool_k),
                "reranked": res.reranked,
                "top5": " ".join(top),
                "errors": json.dumps(res.errors, ensure_ascii=False) if res.errors else "",
            })
    return rows


def summary_markdown(rows: Sequence[dict[str, Any]], metrics: Sequence[str] = METRICS) -> str:
    """Bảng trung bình theo cấu hình, rồi theo (cấu hình, type)."""
    def table(groups: dict[tuple, list[dict]], head: list[str]) -> list[str]:
        lines = ["| " + " | ".join(head + ["n", *metrics]) + " |",
                 "|" + "---|" * (len(head) + 1 + len(metrics))]
        for key, items in groups.items():
            vals = [mean(r[m] for r in items) for m in metrics]
            cells = [f"{v:.3f}" if v is not None else "—" for v in vals]
            lines.append("| " + " | ".join([*key, str(len(items)), *cells]) + " |")
        return lines

    by_config: dict[tuple, list[dict]] = defaultdict(list)
    by_type: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_config[(r["config"],)].append(r)
        by_type[(r["config"], r["type"])].append(r)
    out = ["## Toàn bộ", "", *table(by_config, ["config"]), "",
           "## Theo loại câu hỏi", "", *table(dict(sorted(by_type.items())), ["config", "type"])]
    return "\n".join(out) + "\n"


def answer_rows(questions: Sequence[Question], pipeline: Any) -> list[dict[str, Any]]:
    """Chạy pipeline.ask_debug cho mọi câu (kể cả out_of_scope) — để đo từ chối và chấm tay."""
    rows: list[dict[str, Any]] = []
    for q in questions:
        trace = pipeline.ask_debug(q.question)
        ctx_chunks = [b.chunk for b in trace.context.blocks]
        rows.append({
            "id": q.id,
            "type": q.type,
            "in_scope": q.in_scope,
            "refused": trace.answer.refused,
            "llm_called": trace.llm_called,
            "n_context": len(ctx_chunks),
            "context_has_gold": (any(q.is_relevant(c) for c in ctx_chunks) if q.in_scope else None),
            "answer": trace.answer.text,
            "citations": "; ".join(
                f"[{c.n}] {c.source}" + (f" tr.{c.page}" if c.page is not None else "")
                for c in trace.answer.citations
            ),
            # để chấm tay
            "correct": "",
            "citation_ok": "",
        })
    return rows


def refusal_summary(rows: Sequence[dict[str, Any]]) -> dict[str, float | None]:
    oos = [r for r in rows if not r["in_scope"]]
    ins = [r for r in rows if r["in_scope"]]
    return {
        "refuse_rate_out_of_scope": mean(1.0 if r["refused"] else 0.0 for r in oos),   # càng cao càng tốt
        "refuse_rate_in_scope": mean(1.0 if r["refused"] else 0.0 for r in ins),       # càng thấp càng tốt
        "context_has_gold": mean(
            (1.0 if r["context_has_gold"] else 0.0) for r in ins if r["context_has_gold"] is not None
        ),
        "avg_context_blocks": mean(float(r["n_context"]) for r in ins),
    }


def ragas_rows(questions: Sequence[Question], pipeline: Any) -> list[dict[str, Any]]:
    """Định dạng mẫu của RAGAS (single-turn). Bỏ câu out_of_scope và câu bị từ chối."""
    rows: list[dict[str, Any]] = []
    for q in questions:
        if not q.in_scope:
            continue
        trace = pipeline.ask_debug(q.question)
        if trace.answer.refused:
            continue
        row: dict[str, Any] = {
            "id": q.id,
            "user_input": q.question,
            "retrieved_contexts": [b.chunk.text for b in trace.context.blocks],
            "response": trace.answer.text,
        }
        if q.reference:
            row["reference"] = q.reference
        rows.append(row)
    return rows


DRAFT_SYSTEM = (
    "Bạn soạn ĐÁP ÁN MẪU cho bộ câu hỏi đánh giá. Chỉ dùng nội dung trong TÀI LIỆU, "
    "trả lời ngắn gọn 1-3 câu bằng tiếng Việt, không thêm ý ngoài tài liệu. "
    "Nếu tài liệu không đủ để trả lời, viết: KHÔNG ĐỦ THÔNG TIN."
)


def gold_text(q: Question, store: ChunkStore) -> str:
    """Text của các chunk chứa trang/mục gold (không dùng kết quả retrieval)."""
    parts = [c.text for c in store.all() if q.is_relevant(c)]
    return "\n\n".join(dict.fromkeys(parts))


def draft_reference(q: Question, store: ChunkStore, llm: LLM) -> str | None:
    if not q.in_scope:
        return None
    text = gold_text(q, store)
    if not text:
        return None
    return llm.complete(DRAFT_SYSTEM, f"TÀI LIỆU:\n{text}\n\nCÂU HỎI: {q.question}").strip()


def write_csv(rows: Sequence[dict[str, Any]], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(rows: Iterable[dict[str, Any]], path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


__all__ = [
    "METRICS",
    "RETRIEVAL_CONFIGS",
    "answer_rows",
    "draft_reference",
    "gold_text",
    "ragas_rows",
    "refusal_summary",
    "retrieval_rows",
    "summary_markdown",
    "write_csv",
    "write_jsonl",
]
