"""Evaluate ONE frozen coverage-selection policy using saved v2 evidence only.

All network connections are forbidden. No LLM, embedder, vector index, SDK client,
or live baseline is constructed. Production HybridRetriever/selector are exercised
with saved branch hits, cached decomposition plans, and exact full-input Jev scores.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
from types import SimpleNamespace

from rag.advanced.decomposition import DecompositionPlan
from rag.config import Settings
from rag.eval.metrics import load_questions, recall_at_k, hit_at_k, mrr_at_k
from rag.retrieve.context import ContextConfig, select_context
from rag.retrieve.coverage import CoverageConfig
from rag.retrieve.hybrid import HybridRetriever
from rag.retrieve.rerank import DEFAULT_JEV_MODEL, JEV_INSTRUCTIONS, SCORE_CACHE_SCHEMA, ScoreCache, JevReranker
from rag.schema import Chunk, Hit
from run_rewrite_benchmark import save_json, save_csv, summarize

SOURCE=Path('evals/team-4.2/results/doi-thuong-64q-scenario-decomp-v2')
BRANCH_SOURCE=Path('evals/team-4.2/results/doi-thuong-64q-rewrite-bm25-v1/rewrite-bm25-w03')
QUESTIONS=Path('evals/team-4.2/datasets/benchmark_doi_thuong.jsonl')
DEFAULT_OUT=Path('evals/team-4.2/results/doi-thuong-64q-coverage-v1')
POLICY=CoverageConfig(anchor_k=2,min_p=.5,weight=.25,branch_k=5)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_network(*args,**kwargs):
    raise RuntimeError('Offline coverage benchmark forbids all network access')


class SavedDense:
    def __init__(self,queries): self.queries=queries; self.calls=0
    def build(self,chunks): pass
    def search(self,query,k):
        self.calls+=1
        return [Hit(cid,0.,rank,'dense') for rank,cid in enumerate(self.queries[query][:k],1)]


class ForbiddenBM25:
    def build(self,chunks): pass
    def search(self,*args,**kwargs): raise RuntimeError('BM25 must not run in v2 replay')


class CachedJev:
    def __init__(self,data):
        self.db=sqlite3.connect((data/'cache/rerank.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
        self.scores={}

    def rerank(self,query,hits,chunks,k):
        scored=[]
        for hit in hits:
            chunk=chunks[hit.chunk_id]
            key=ScoreCache.key(DEFAULT_JEV_MODEL,query,chunk,instructions=JEV_INSTRUCTIONS,
                state=JevReranker.build_state(query,chunk))
            value=self.db.execute('SELECT score FROM rerank_scores WHERE key=?',(key,)).fetchone()
            if value is None: raise RuntimeError('Missing Jev score; no API fallback')
            self.scores[key]=value[0]
            scored.append((hit,value[0]))
        scored.sort(key=lambda pair:(-pair[1],pair[0].rank))
        return [Hit(hit.chunk_id,score,rank,'rerank') for rank,(hit,score) in enumerate(scored[:k],1)]


def metrics(q,ranked,chunks):
    ids=[h.chunk_id for h in ranked]
    return {'recall@5':recall_at_k(q,ids,chunks,5),'hit@5':hit_at_k(q,ids,chunks,5),
            'mrr@5':mrr_at_k(q,ids,chunks,5),'recall@20':recall_at_k(q,ids,chunks,20),
            'candidate_recall':recall_at_k(q,ids,chunks,len(ids))}


def context_stats(q,ranked,chunks,cfg):
    selected=select_context(ranked,chunks,cfg)
    return {'empty':selected.empty,'blocks':len(selected.blocks),
        'whitespace_units':sum(len(b.chunk.text.split()) for b in selected.blocks),
        'full_gold':all(any(g.matches(b.chunk) for b in selected.blocks) for g in q.gold),
        'chunk_ids':selected.chunk_ids}


def main():
    socket.create_connection=reject_network
    socket.socket.connect=reject_network
    socket.socket.connect_ex=reject_network
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=DEFAULT_OUT)
    args=parser.parse_args(); out=args.out
    assert not out.exists(),'Use a fresh output; never overwrite a previous benchmark'
    source_meta=read_json(SOURCE/'config.json')
    assert sha(QUESTIONS)==source_meta['questions_sha256']
    assert source_meta['rerank_instructions_sha256']==hashlib.sha256(JEV_INSTRUCTIONS.encode()).hexdigest()
    assert source_meta['rerank_model']==DEFAULT_JEV_MODEL
    data=Path(source_meta['data_dir']); chunk_path=data/'processed/chunks.jsonl'
    assert sha(chunk_path)==source_meta['index_snapshot']['chunks_sha256']
    chunks={c.chunk_id:c for c in (Chunk.from_dict(json.loads(line)) for line in
        chunk_path.read_text(encoding='utf-8').splitlines() if line.strip())}
    source={t['id']:t for t in read_json(SOURCE/'query_traces.json')}
    raw={t['id']:t for t in read_json(BRANCH_SOURCE/'query_traces.json')}
    with (SOURCE/'retrieval_per_question.csv').open(encoding='utf-8-sig',newline='') as f:
        reference={row['id']:row for row in csv.DictReader(f)}
    questions=load_questions(QUESTIONS)
    assert len(questions)==len(source)==len(reference)==64
    query_hits={}; plans={}
    for t in source.values():
        assert t['queries']==raw[t['id']]['queries'] and not t['errors']
        plans[t['question']]=t['queries']
        for i,query in enumerate(t['queries']):
            ids=raw[t['id']]['arms']['dense' if len(t['queries'])==1 else f'q{i}_dense']
            if query in query_hits: assert query_hits[query]==ids
            query_hits[query]=ids
    dense=SavedDense(query_hits); ranker=CachedJev(data)
    retriever=HybridRetriever(ForbiddenBM25(),dense,reranker=ranker,
        arm_k=source_meta['arm_k'],rrf_k=source_meta['rrf_k'],rerank_n=source_meta['rerank_n'],
        merge_articles=source_meta['merge_articles'],article_pool_factor=source_meta['article_pool_factor'],
        coverage=POLICY)
    decomp=source_meta['decomposition']
    retriever.decomposer=SimpleNamespace(**decomp,plan=lambda query:DecompositionPlan(list(plans[query])))
    retriever.build(chunks.values())
    settings=Settings.load()
    context_cfg=ContextConfig(min_p=settings.context_min_p,max_blocks=settings.context_max_blocks,
        max_words=settings.context_max_words,fixed_k=source_meta['top_k'])
    out.mkdir(parents=True)
    save_json(out/'config.json',{'config':'v2+coverage-v1','coverage':asdict(POLICY),
        'source':str(SOURCE),'source_config_sha256':sha(SOURCE/'config.json'),
        'source_traces_sha256':sha(SOURCE/'query_traces.json'),'branch_source':str(BRANCH_SOURCE),
        'branch_traces_sha256':sha(BRANCH_SOURCE/'query_traces.json'),'chunks_sha256':sha(chunk_path),
        'questions_sha256':sha(QUESTIONS),'rerank_model':DEFAULT_JEV_MODEL,
        'rerank_instructions_sha256':hashlib.sha256(JEV_INSTRUCTIONS.encode()).hexdigest(),
        'score_cache_schema':SCORE_CACHE_SCHEMA,'selector_code_sha256':sha(Path('app/team-4.2/src/rag/retrieve/coverage.py')),
        'context_config':asdict(context_cfg),'context_note':'Same current context settings for before/after offline simulation; no answer evaluation.',
        'network_forbidden':True,'model_api_calls':0,'baseline_execution':False,
        'policy_frozen_before_evaluation':True,'parameter_sweep':False})
    rows,details,changes=[],[],[]
    for i,q in enumerate(questions,1):
        result=retriever.retrieve(q.question,source_meta['top_k'],mode='dense')
        assert not result.errors and result.reranked
        ids=[h.chunk_id for h in result.candidates]
        assert ids==source[q.id]['candidates'],f'Pool mismatch: {q.id}'
        before=result.pre_selection_ranked or result.ranked
        assert [h.chunk_id for h in before[:5]]==source[q.id]['top5']
        original_metrics=metrics(q,before,chunks)
        for metric,value in original_metrics.items():
            assert abs(value-float(reference[q.id][metric]))<1e-12,(q.id,metric)
        assert [h.chunk_id for h in result.ranked[:POLICY.anchor_k]]==[h.chunk_id for h in before[:POLICY.anchor_k]]
        assert {(h.chunk_id,h.score,h.merged) for h in result.ranked}=={(h.chunk_id,h.score,h.merged) for h in before}
        old_positions={h.chunk_id:j for j,h in enumerate(before)}
        assert all(h.score>=POLICY.min_p for h in result.hits if old_positions[h.chunk_id]>=5)
        measured=metrics(q,result.ranked,chunks)
        assert measured['candidate_recall']==original_metrics['candidate_recall']
        rows.append({'id':q.id,'type':q.type,'author':q.author,'config':'v2+coverage-v1',**measured,
            'reranked':True,'errors':'{}','query_count':len(result.queries),'candidate_chunks':len(ids),
            'selection_policy':result.selection_policy,'top5':' '.join(h.chunk_id for h in result.hits),
            'jev_cache_misses':0})
        delta={m:measured[m]-original_metrics[m] for m in measured}
        if any(abs(value)>1e-12 for value in delta.values()):
            changes.append({'id':q.id,'question':q.question,'before':original_metrics,'after':measured,'delta':delta})
        details.append({'id':q.id,'question':q.question,'queries':result.queries,'candidates':ids,
            'selection_policy':result.selection_policy,
            'before':[{'chunk_id':h.chunk_id,'score':h.score,'rank':h.rank,'merged':list(h.merged)} for h in before],
            'ranked':[{'chunk_id':h.chunk_id,'score':h.score,'rank':h.rank,'merged':list(h.merged)} for h in result.ranked],
            'context_before':context_stats(q,before,chunks,context_cfg),
            'context_after':context_stats(q,result.ranked,chunks,context_cfg)})
        print(f'[{i}/64] {q.id}: R5={measured["recall@5"]:.3f}, changed={[h.chunk_id for h in before[:5]]!=[h.chunk_id for h in result.hits]}',flush=True)
    save_csv(out/'retrieval_per_question.csv',rows)
    save_json(out/'query_traces.json',details)
    save_json(out/'paired_changes.json',changes)
    summary={'saved-v2':summarize(list(reference.values())),'v2+coverage-v1':summarize(rows)}
    save_json(out/'summary.json',summary)
    save_json(out/'summary_by_type.json',{kind:{'saved-v2':summarize([r for r in reference.values() if r['type']==kind]),
        'v2+coverage-v1':summarize([r for r in rows if r['type']==kind])} for kind in ('multi','paraphrase')})
    ctx={stage:{'empty':sum(t[f'context_{stage}']['empty'] for t in details),
        'full_gold':sum(t[f'context_{stage}']['full_gold'] for t in details),
        'mean_blocks':sum(t[f'context_{stage}']['blocks'] for t in details)/64,
        'mean_whitespace_units':sum(t[f'context_{stage}']['whitespace_units'] for t in details)/64}
        for stage in ('before','after')}
    save_json(out/'context_summary.json',ctx)
    save_json(out/'verification.json',{'questions':64,'source_pool_replayed_exactly':64,
        'saved_reference_metrics_recomputed_exactly':64,'same_jev_scores_and_merged_ids':True,
        'anchors_preserved':True,'candidate_recall_preserved':True,'promoted_hits_pass_min_p':True,
        'cached_dense_branch_searches':dense.calls,'full_input_cache_pairs_found':len(ranker.scores),
        'score_cache_snapshot_sha256':hashlib.sha256(json.dumps(sorted(ranker.scores.items())).encode()).hexdigest(),
        'network_forbidden':True,'model_api_calls':0,'baseline_execution':False,'parameter_sweep':False})
    lines=['# Coverage selection v1 — benchmark offline 64 câu','',
        'Chỉ thử một policy cố định trên pool/điểm Jev của v2. Không gọi API; baseline chỉ đọc kết quả đã lưu.','',
        '| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |',
        '|---|---:|---:|---:|---:|---:|']
    for name,m in summary.items():
        lines.append(f'| {name} | {m["recall@5"]:.6f} | {m["hit@5"]:.6f} | {m["mrr@5"]:.6f} | {m["recall@20"]:.6f} | {m["multi_full_gold_top5"]}/27 |')
    lines.extend(['',f'Policy: {asdict(POLICY)}. Điểm kết hợp chỉ dùng để chọn, không ghi đè xác suất Jev.',
        'Branch rank là tín hiệu thay thế cho độ phủ, chưa chứng minh bằng chứng thực sự hỗ trợ ý đó.',
        'Context được mô phỏng trước/sau bằng cùng cấu hình hiện tại; chưa sinh hoặc chấm câu trả lời.',
        'Tập 64 câu đã dùng để phát triển; chưa đánh giá tập độc lập. Không sửa tham số sau khi xem kết quả.'])
    (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    ranker.db.close()
    print(json.dumps({'summary':summary,'context':ctx},indent=2))


if __name__=='__main__': main()
