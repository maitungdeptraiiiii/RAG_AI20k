"""One ablation: frozen BM25=.3 pools, Jev uses original question. No retrieval.

Only Jev cache misses may use the network. No LLM, embedder, vector store or retriever
is created. Saved comparisons are read only. --stage verify forbids network access.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import time

from rag.config import Settings
from rag.eval.metrics import load_questions, recall_at_k, hit_at_k, mrr_at_k
from rag.retrieve.merge import merge_by_article
from rag.retrieve.rerank import DEFAULT_JEV_MODEL, JEV_INSTRUCTIONS, SCORE_CACHE_SCHEMA, JevReranker, ScoreCache
from rag.schema import Chunk, Hit
from run_rewrite_benchmark import save_json, save_csv, summarize

SOURCE=Path('evals/team-4.2/results/doi-thuong-64q-rewrite-bm25-v1/rewrite-bm25-w03')
SAVED_V2=Path('evals/team-4.2/results/doi-thuong-64q-scenario-decomp-v2')
QUESTIONS=Path('evals/team-4.2/datasets/benchmark_doi_thuong.jsonl')
OUT=Path('evals/team-4.2/results/doi-thuong-64q-bm25-w03-original-rerank')
NAME='bm25-w03-original-rerank'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_rows(directory):
    with (directory/'retrieval_per_question.csv').open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def load_inputs():
    meta=read_json(SOURCE/'config.json')
    questions=load_questions(QUESTIONS)
    traces=read_json(SOURCE/'query_traces.json')
    assert len(questions)==len(traces)==64
    assert [q.id for q in questions]==[t['id'] for t in traces]
    assert meta['bm25_rrf_weight']==.3 and meta['dense_rrf_weight']==1
    assert meta['rerank_instructions_sha256']==hashlib.sha256(JEV_INSTRUCTIONS.encode()).hexdigest()
    assert meta['questions_sha256']==sha(QUESTIONS)
    data=Path(meta['data_dir'])
    chunk_path=data/'processed/chunks.jsonl'
    assert sha(chunk_path)==read_json(data/'snapshot_manifest.json')['chunks_sha256']
    chunks={c.chunk_id:c for c in (Chunk.from_dict(json.loads(line)) for line in
        chunk_path.read_text(encoding='utf-8').splitlines() if line.strip())}
    for q,t in zip(questions,traces):
        assert q.question==t['question'] and not t['errors']
        assert len(t['candidates'])==len(set(t['candidates']))
        assert all(cid in chunks for cid in t['candidates'])
    provenance={'config':NAME,'source_run':str(SOURCE),'source_config_sha256':sha(SOURCE/'config.json'),
        'source_traces_sha256':sha(SOURCE/'query_traces.json'),
        'source_rows_sha256':sha(SOURCE/'retrieval_per_question.csv'),'questions_sha256':sha(QUESTIONS),
        'chunks_sha256':sha(chunk_path),'data_dir':str(data),'top_k':meta['top_k'],
        'rerank_model':DEFAULT_JEV_MODEL,'rerank_instructions':JEV_INSTRUCTIONS,
        'rerank_instructions_sha256':hashlib.sha256(JEV_INSTRUCTIONS.encode()).hexdigest(),
        'score_cache_schema':SCORE_CACHE_SCHEMA,'rerank_query':'original question',
        'bm25_rrf_weight':.3,'dense_rrf_weight':1.,
        'pool_strategy':'exact frozen source candidates and order',
        'baseline_execution':False,'retrieval_execution':False,'rewrite_execution':False,
        'hyde_execution':False,'embedding_execution':False,'answer_generation':False,
        'note':'Retrieval metrics only. Cache reuse affects request counts and elapsed times.'}
    return questions,traces,chunks,data,provenance


def score_keys(query,ids,chunks):
    return [ScoreCache.key(DEFAULT_JEV_MODEL,query,chunks[cid],instructions=JEV_INSTRUCTIONS,
        state=JevReranker.build_state(query,chunks[cid])) for cid in ids]


def preflight(questions,traces,chunks,cache):
    missing={}
    for q,t in zip(questions,traces):
        keys=score_keys(q.question,t['candidates'],chunks)
        found=cache.get_many(keys)
        missing[q.id]=[key for key in keys if key not in found]
    print(json.dumps({'questions':64,'candidate_pairs':sum(len(t['candidates']) for t in traces),
        'cached_pairs':sum(len(t['candidates'])-len(missing[q.id]) for q,t in zip(questions,traces)),
        'missing_pairs':sum(len(v) for v in missing.values()),
        'retrieval_calls':0,'llm_calls':0,'embedding_calls':0,'baseline_execution':False},indent=2),flush=True)
    return missing


def run(out,*,resume=False):
    questions,traces,chunks,data,provenance=load_inputs()
    Settings.load()  # Load existing API credentials, without printing or constructing an LLM.
    cache=ScoreCache(data/'cache/rerank.sqlite')
    out.mkdir(parents=True,exist_ok=True)
    rows,details=[],[]
    if resume:
        saved=read_json(out/'config.json')
        assert saved['provenance']==provenance,'Cannot resume changed inputs or model'
        initial_missing=saved['initial_missing_keys']
        rows=read_rows(out); details=read_json(out/'query_traces.json')
        common=min(len(rows),len(details))
        assert [r['id'] for r in rows[:common]]==[t['id'] for t in details[:common]]==[q.id for q in questions[:common]]
        rows=rows[:common]; details=details[:common]
    else:
        assert not (out/'config.json').exists(),'Existing run; use --resume'
        initial_missing=preflight(questions,traces,chunks,cache)
        save_json(out/'config.json',{'provenance':provenance,'initial_missing_keys':initial_missing})
    reranker=JevReranker(DEFAULT_JEV_MODEL,cache=cache)  # Strict: no fallback reranker.
    completed=len(rows)
    for i,(q,t) in enumerate(zip(questions,traces),1):
        if i<=completed: continue
        start=time.perf_counter()
        candidates=[Hit(cid,0.,rank,'fused') for rank,cid in enumerate(t['candidates'],1)]
        ranked=merge_by_article(reranker.rerank(q.question,candidates,chunks,len(candidates)),chunks)
        pool=[h.chunk_id for h in ranked]; top=pool[:provenance['top_k']]
        rows.append({'id':q.id,'type':q.type,'author':q.author,'config':NAME,
            'recall@5':recall_at_k(q,top,chunks,5),'hit@5':hit_at_k(q,top,chunks,5),
            'mrr@5':mrr_at_k(q,top,chunks,5),'recall@20':recall_at_k(q,pool,chunks,20),
            'candidate_recall':recall_at_k(q,pool,chunks,len(pool)),
            'reranked':True,'errors':'{}','query_count':len(t['queries']),
            'candidate_chunks':len(candidates),'jev_cache_misses':len(initial_missing[q.id]),
            'elapsed_s':round(time.perf_counter()-start,3),'top5':' '.join(top)})
        details.append({'id':q.id,'question':q.question,'rerank_query':q.question,
            'bm25_rewrite':t['rewrite'],'queries':t['queries'],'candidates':t['candidates'],
            'ranked':[{'chunk_id':h.chunk_id,'score':h.score,'rank':h.rank,'merged':list(h.merged)} for h in ranked],
            'top5':top,'errors':{}})
        save_csv(out/'retrieval_per_question.csv',rows)
        save_json(out/'query_traces.json',details)
        print(f'[{i}/64] {q.id}: R5={rows[-1]["recall@5"]:.3f}, initial_missing={len(initial_missing[q.id])}',flush=True)
    cache.close()
    assert len(rows)==64
    print(json.dumps(summarize(rows),indent=2),flush=True)


def verify(out):
    def reject_network(*args,**kwargs): raise RuntimeError('Offline verification forbids network')
    socket.create_connection=reject_network
    socket.socket.connect=reject_network
    questions,source,chunks,data,provenance=load_inputs()
    meta=read_json(out/'config.json')
    assert meta['provenance']==provenance
    rows=read_rows(out); traces=read_json(out/'query_traces.json')
    assert len(rows)==len(traces)==64
    db=sqlite3.connect((data/'cache/rerank.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    for q,old,t,row in zip(questions,source,traces,rows):
        assert q.id==old['id']==t['id']==row['id']
        assert t['candidates']==old['candidates'] and t['queries']==old['queries']
        assert t['bm25_rewrite']==old['rewrite'] and t['rerank_query']==q.question
        assert row['reranked']=='True' and json.loads(row['errors'])==t['errors']=={}
        scored=[]
        for rank,(cid,key) in enumerate(zip(t['candidates'],score_keys(q.question,t['candidates'],chunks)),1):
            found=db.execute('SELECT score FROM rerank_scores WHERE key=?',(key,)).fetchone()
            assert found is not None,(q.id,cid)
            scored.append(Hit(cid,found[0],rank,'rerank'))
        ranked=merge_by_article(sorted(scored,key=lambda h:(-h.score,h.rank)),chunks)
        pool=[h.chunk_id for h in ranked]
        assert pool==[h['chunk_id'] for h in t['ranked']]
        assert all(h.score==saved['score'] and list(h.merged)==saved['merged'] for h,saved in zip(ranked,t['ranked']))
        assert pool[:provenance['top_k']]==t['top5']==row['top5'].split()
        for metric,fn,k in [('recall@5',recall_at_k,5),('hit@5',hit_at_k,5),('mrr@5',mrr_at_k,5),
                            ('recall@20',recall_at_k,20),('candidate_recall',recall_at_k,len(pool))]:
            assert abs(fn(q,pool,chunks,k)-float(row[metric]))<1e-12,(q.id,metric)
        old_row=next(r for r in read_rows(SOURCE) if r['id']==q.id)
        assert row['candidate_recall']==old_row['candidate_recall']
    db.close()
    save_json(out/'verification.json',{'questions':64,'network_disabled':True,
        'all_metrics_and_ranks_recomputed':True,'all_full_input_v2_cache_scores_found':True,
        'exact_source_pool_and_order':True,'same_bm25_rewrites_and_decomposition_queries':True,
        'baseline_execution':False,'retrieval_execution':False})
    print('Offline verification passed for all 64 questions.')


def report(out):
    datasets={'saved-v2':read_rows(SAVED_V2),'bm25-w03-rewrite-rerank':read_rows(SOURCE),NAME:read_rows(out)}
    summaries={name:summarize(rows) for name,rows in datasets.items()}
    save_json(out/'summary.json',summaries)
    save_json(out/'summary_by_type.json',{name:{kind:summarize([r for r in rows if r['type']==kind])
        for kind in ('multi','paraphrase')} for name,rows in datasets.items()})
    paired={}
    for name,old in datasets.items():
        if name==NAME: continue
        old={r['id']:r for r in old}; changed=[]
        for row in datasets[NAME]:
            delta={m:float(row[m])-float(old[row['id']][m]) for m in ('recall@5','hit@5','mrr@5','candidate_recall')}
            if any(abs(d)>1e-12 for d in delta.values()):
                changed.append({'id':row['id'],'type':row['type'],'delta':delta,
                    'before':{m:float(old[row['id']][m]) for m in delta},
                    'after':{m:float(row[m]) for m in delta}})
        paired[name]={'changed':changed,'counts':{m:{
            'wins':sum(r['delta'][m]>1e-12 for r in changed),
            'losses':sum(r['delta'][m]<-1e-12 for r in changed),
            'ties':64-sum(abs(r['delta'][m])>1e-12 for r in changed)} for m in ('recall@5','mrr@5')}}
    save_json(out/'paired_changes.json',paired)
    lines=['# BM25 0.3, Jev nhận câu gốc — benchmark 64 câu','',
        'Chỉ chạy một cấu hình mới trên pool cố định của BM25=0.3. Các cấu hình đối chiếu đọc từ kết quả đã lưu.',
        'Không chạy lại baseline, retrieval, rewrite, HyDE hoặc embedding.','',
        '| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |',
        '|---|---:|---:|---:|---:|---:|']
    for name,m in summaries.items():
        lines.append(f'| {name} | {m["recall@5"]:.6f} | {m["hit@5"]:.6f} | {m["mrr@5"]:.6f} | {m["recall@20"]:.6f} | {m["multi_full_gold_top5"]}/27 |')
    lines.extend(['','## Thay đổi Recall@5',''])
    for name,pair in paired.items():
        wins=[r['id'] for r in pair['changed'] if r['delta']['recall@5']>1e-12]
        losses=[r['id'] for r in pair['changed'] if r['delta']['recall@5']<-1e-12]
        lines.append(f'- So với {name}: tăng {wins}; giảm {losses}.')
    new=summaries[NAME]
    lines.extend(['',f'Tổng {new["candidate_chunks"]} cặp query–chunk; {new["jev_cache_misses"]} cặp thiếu cache ở preflight.',
        'Cache key gồm model, toàn bộ instructions/state và chunk_id. Số cặp thiếu cache không tính retry SDK hoặc hóa đơn.',
        'Chỉ đánh giá retrieval, chưa đánh giá câu trả lời hoặc tập độc lập. Thời gian bị ảnh hưởng cache.',
        'Đã thêm REWRITE_FOR_RERANK=false để chỉ dùng rewrite cho BM25; chưa thay đổi .env.'])
    (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(summaries,indent=2))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['preflight','run','verify','report'],required=True)
    ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--resume',action='store_true')
    args=ap.parse_args()
    if args.stage=='preflight':
        questions,traces,chunks,data,_=load_inputs()
        cache=ScoreCache(data/'cache/rerank.sqlite')
        preflight(questions,traces,chunks,cache); cache.close()
    elif args.stage=='run': run(args.out,resume=args.resume)
    elif args.stage=='verify': verify(args.out)
    else: report(args.out)


if __name__=='__main__': main()
