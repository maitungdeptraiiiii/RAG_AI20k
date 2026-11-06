"""Run only requested rewrite/BM25 ablations, reusing saved dense retrieval and plans.

Stages are sequential: prepare, dense, hybrid, weighted, report.
No baseline execution. The dense stage reranks the exact saved v2 candidate pools.
Hybrid stages use cache-only HyDE/embeddings/plans: only new Jev pairs can call APIs.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import csv
import hashlib
import json
from pathlib import Path
import time

from rag.advanced.rewrite import QueryRewriter, REWRITE_SYSTEM
from rag.config import Settings
from rag.eval.metrics import load_questions, recall_at_k, hit_at_k, mrr_at_k
from rag.eval.runner import write_csv
from rag.generate.llm import LLMCache, OpenAIChatLLM
from rag.index.embedder import EmbeddingCache
from rag.pipeline import RAGPipeline
from rag.retrieve.hybrid import RetrievalResult
from rag.retrieve.merge import article_key, merge_by_article, take_articles
from rag.retrieve.fusion import rrf
from rag.retrieve.rerank import ScoreCache, JevReranker, JEV_INSTRUCTIONS
from rag.schema import Hit

SOURCE=Path('evals/team-4.2/results/doi-thuong-64q-scenario-decomp-v2')
QUESTIONS=Path('evals/team-4.2/datasets/benchmark_doi_thuong.jsonl')
DEFAULT_OUT=Path('evals/team-4.2/results/doi-thuong-64q-rewrite-bm25-v1')
STAGES={'dense':('rewrite-only',0.),'hybrid':('rewrite-bm25-w1',1.),
        'weighted':('rewrite-bm25-w03',.3)}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path,value):
    temporary=path.with_name(path.name+'.tmp')
    for attempt in range(4):
        try:
            temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            temporary.replace(path)
            return
        except OSError:
            if attempt==3: raise
            time.sleep(.25*(attempt+1))


def save_csv(path,rows):
    temporary=path.with_name(path.name+'.tmp')
    for attempt in range(4):
        try:
            write_csv(rows,temporary)
            temporary.replace(path)
            return
        except OSError:
            if attempt==3: raise
            time.sleep(.25*(attempt+1))


def make_llm(s):
    return OpenAIChatLLM(s.llm_model,temperature=s.llm_temperature,
        base_url=s.llm_base_url,api_key=s.llm_api_key,cache=LLMCache(s.cache_dir/'llm.sqlite'))


class CacheOnlyLLM:
    def __init__(self,s):
        self.s=s
        self.cache=LLMCache(s.cache_dir/'llm.sqlite')

    def complete(self,system,user):
        messages=[{'role':'system','content':system},{'role':'user','content':user}]
        value=self.cache.get(LLMCache.key(self.s.llm_model,self.s.llm_temperature,messages))
        if value is None:
            raise RuntimeError('LLM cache miss: benchmark forbids regenerating plans/HyDE/rewrites')
        return value


class CacheOnlyEmbedder:
    def __init__(self,s):
        self.model_id=s.embed_model; self.dim=s.embed_dim
        self.cache=EmbeddingCache(s.cache_dir/'embeddings.sqlite')

    def embed_query(self,texts):
        keys=[EmbeddingCache.key(self.model_id+'#retrieval.query',t) for t in texts]
        found=self.cache.get_many(keys)
        if any(k not in found for k in keys):
            raise RuntimeError('Embedding cache miss; no API fallback')
        return [found[k] for k in keys]

    def embed(self,texts):
        raise RuntimeError('Corpus embedding forbidden in benchmark')


def public_metadata(s):
    return {'llm':s.llm_model,'llm_temperature':s.llm_temperature,'advanced':s.advanced,
        'data_dir':str(s.data_dir),'arm_k':s.arm_k,'rerank_n':s.rerank_n,'rrf_k':s.rrf_k,
        'article_pool_factor':s.article_pool_factor,'merge_articles':s.merge_articles,'top_k':s.top_k,
        'index_signature':read_json(s.index_config_path),
        'decomposition':{'max_subqueries':s.decomp_max_subqueries,'include_original':s.decomp_include_original,
            'per_query_k':s.decomp_per_query_k,'pool_size':s.decomp_pool_size,
            'max_new_articles':s.decomp_max_new_articles},
        'rewrite_system_prompt':REWRITE_SYSTEM,
        'rewrite_prompt_sha256':hashlib.sha256(REWRITE_SYSTEM.encode()).hexdigest(),
        'rerank_instructions_sha256':hashlib.sha256(JEV_INSTRUCTIONS.encode()).hexdigest(),
        'questions_sha256':hashlib.sha256(QUESTIONS.read_bytes()).hexdigest(),
        'source_traces_sha256':hashlib.sha256((SOURCE/'query_traces.json').read_bytes()).hexdigest(),
        'baseline_execution':False,'source_run':str(SOURCE)}


def prepare(s,out):
    meta=public_metadata(s)
    if (out/'config.json').exists():
        assert read_json(out/'config.json')==meta,'Changed prepare settings; use a new output'
    else:
        save_json(out/'config.json',meta)
    # Resume cached preparation without calling the same rewrite twice.
    records=read_json(out/'rewrites.json') if (out/'rewrites.json').exists() else []
    previous={r['id']:r for r in records}
    rewriter=QueryRewriter(make_llm(s))
    questions=load_questions(QUESTIONS)
    for i,q in enumerate(questions,1):
        if q.id in previous:
            assert previous[q.id]['original']==q.question
            continue
        result=rewriter.rewrite(q.question)
        records.append({'id':q.id,'original':q.question,'rewrite':result.query,'error':result.error})
        save_json(out/'rewrites.json',records)
        print(f'[rewrite {i}/64] {q.id}: changed={result.query!=q.question}, error={result.error}',flush=True)
    assert len(records)==64
    assert all(not r['error'] or r['rewrite']==r['original'] for r in records)
    print(f'Prepared 64 plans; conservative original-query fallbacks: {sum(bool(r["error"]) for r in records)}',flush=True)


def run_stage(s,out,stage,*,resume=False):
    meta=read_json(out/'config.json')
    assert meta==public_metadata(s),'Settings differ from preparation'
    source=read_json(SOURCE/'config.json')
    assert hashlib.sha256(s.chunks_path.read_bytes()).hexdigest()==source['index_snapshot']['chunks_sha256']
    for key in ('questions_sha256','index_signature','advanced','llm','rerank_instructions_sha256',
                'arm_k','rerank_n','rrf_k','article_pool_factor','merge_articles','top_k','decomposition'):
        assert meta[key]==source[key],f'Source config mismatch: {key}'
    rewrites={r['id']:r for r in read_json(out/'rewrites.json')}
    assert len(rewrites)==64
    assert all(not r['error'] or r['rewrite']==r['original'] for r in rewrites.values())
    name,weight=STAGES[stage]
    directory=out/name; directory.mkdir(exist_ok=True)
    assert resume or not (directory/'config.json').exists(),'Stage already started; use --resume to continue checkpoints'
    llm=CacheOnlyLLM(s)
    p=RAGPipeline.from_settings(s,llm=llm)
    r=p.retriever
    assert set(r.arms)=={'dense','bm25'}
    r.arms['dense'].fallback=False
    r.arms['dense'].dense.embedder=CacheOnlyEmbedder(s)
    # Abort on Jev failure instead of silently using a fallback ranking.
    r.reranker=r.reranker.primary
    r.bm25_rrf_weight=weight
    traces={t['id']:t for t in read_json(SOURCE/'query_traces.json')}
    questions=load_questions(QUESTIONS)
    stage_meta={**meta,'config':name,'bm25_rrf_weight':weight,
        'dense_rrf_weight':1.,'mode':'frozen-dense-pool' if stage=='dense' else 'hybrid',
        'rerank_query':'full-question rewrite','bm25_query':'original branch: rewrite; child branches: unchanged child',
        'pool_strategy':'frozen exact v2 pool' if stage=='dense' else '20 original-query hybrid articles + at most 10 novel child articles',
        'retrieval_llm_and_embeddings':'cache-only, abort on miss',
        'note':'Retrieval only. API/cost/latency affected by shared cache; no answer generation.'}
    if resume:
        assert read_json(directory/'config.json')==stage_meta,'Cannot resume different configuration'
    else:
        save_json(directory/'config.json',stage_meta)
    rows,details,orphan_rows=[],[],{}
    if resume:
        with (directory/'retrieval_per_question.csv').open(encoding='utf-8-sig',newline='') as f:
            old_rows=list(csv.DictReader(f))
        details=read_json(directory/'query_traces.json')
        common=min(len(old_rows),len(details))
        assert [r['id'] for r in old_rows[:common]]==[t['id'] for t in details[:common]]==[q.id for q in questions[:common]]
        orphan_rows={r['id']:r for r in old_rows[common:]}
        rows=old_rows[:common]; details=details[:common]
        print(f'Resuming {name}: {common}/64 complete; cached scores retained.',flush=True)
    completed=len(rows)
    for i,q in enumerate(questions,1):
        if i<=completed: continue
        start=time.perf_counter(); rewritten=rewrites[q.id]['rewrite']
        if stage=='dense':
            old=traces[q.id]
            result=RetrievalResult(query=q.question,mode='dense',queries=old['queries'],rerank_query=rewritten,
                candidates=[Hit(cid,0.,rank,'fused') for rank,cid in enumerate(old['candidates'],1)])
        else:
            # Build actual hybrid candidates through production code, without scoring yet.
            result=r.retrieve(q.question,s.top_k,mode='hybrid',rerank=False)
            assert result.rerank_query==rewritten and result.queries==traces[q.id]['queries']
            if rewrites[q.id]['error']:
                assert result.errors.get('rewrite')==rewrites[q.id]['error']
                del result.errors['rewrite']
        assert not result.errors,(q.id,result.errors)
        keys=[ScoreCache.key(r.reranker.model_id,rewritten,r.chunks[h.chunk_id],
            instructions=r.reranker.instructions,state=JevReranker.build_state(rewritten,r.chunks[h.chunk_id]))
            for h in result.candidates]
        misses=len(keys)-len(r.reranker.cache.get_many(keys))
        misses+=int(orphan_rows.get(q.id,{}).get('jev_cache_misses',0))
        result=r._rank_result(result,s.top_k,True)
        assert result.reranked and not result.errors
        top=[h.chunk_id for h in result.hits]; pool=[h.chunk_id for h in result.ranked]
        rows.append({'id':q.id,'type':q.type,'author':q.author,'config':name,
            'recall@5':recall_at_k(q,top,r.chunks,5),'hit@5':hit_at_k(q,top,r.chunks,5),
            'mrr@5':mrr_at_k(q,top,r.chunks,5),'recall@20':recall_at_k(q,pool,r.chunks,20),
            'candidate_recall':recall_at_k(q,pool,r.chunks,len(pool)),
            'reranked':True,'errors':'{}','query_count':len(result.queries),
            'rewrite_warning':rewrites[q.id]['error'] or '',
            'candidate_chunks':len(result.candidates),'jev_cache_misses':misses,
            'elapsed_s':round(time.perf_counter()-start,3),'top5':' '.join(top)})
        details.append({'id':q.id,'question':q.question,'rewrite':rewritten,'queries':result.queries,
            'candidates':[h.chunk_id for h in result.candidates],
            'ranked':[{'chunk_id':h.chunk_id,'score':h.score,'rank':h.rank,'merged':list(h.merged)} for h in result.ranked],
            'top5':top,'errors':result.errors,
            'rewrite_warning':rewrites[q.id]['error'],
            'arms':{arm:[h.chunk_id for h in hits] for arm,hits in result.arms.items()}})
        if q.id in orphan_rows:
            assert all(str(rows[-1][m])==str(orphan_rows[q.id][m]) for m in
                ('top5','recall@5','hit@5','mrr@5','candidate_chunks')),'Resumed ranking changed'
        save_csv(directory/'retrieval_per_question.csv',rows)
        save_json(directory/'query_traces.json',details)
        print(f'[{name} {i}/64] {q.id}: R5={rows[-1]["recall@5"]:.3f}, new_jev_pairs={misses}',flush=True)
    assert len(rows)==64
    print(json.dumps(summarize(rows),ensure_ascii=False,indent=2),flush=True)


def summarize(rows):
    return {'n':len(rows),**{m:sum(float(r[m]) for r in rows)/len(rows)
        for m in ('recall@5','hit@5','mrr@5','recall@20','candidate_recall')},
        'full_gold_top5':sum(float(r['recall@5'])==1 for r in rows),
        'multi_full_gold_top5':sum(r['type']=='multi' and float(r['recall@5'])==1 for r in rows),
        'candidate_chunks':sum(int(r['candidate_chunks']) for r in rows),
        'rewrite_fallbacks':sum(bool(r.get('rewrite_warning')) for r in rows),
        'jev_cache_misses':(sum(int(r['jev_cache_misses']) for r in rows)
                            if all('jev_cache_misses' in r for r in rows) else None)}


def report(out):
    datasets={}
    for name,directory in [('saved-v2',SOURCE),*((name,out/name) for name,_ in STAGES.values())]:
        with (directory/'retrieval_per_question.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        assert len(rows)==64 and len({r['id'] for r in rows})==64
        assert all(r['reranked']=='True' and json.loads(r['errors'])=={} for r in rows)
        datasets[name]=rows
    summary={name:summarize(rows) for name,rows in datasets.items()}
    save_json(out/'summary.json',summary)
    by_type={name:{kind:summarize([r for r in rows if r['type']==kind])
        for kind in ('multi','paraphrase')} for name,rows in datasets.items()}
    save_json(out/'summary_by_type.json',by_type)
    paired={}
    for reference,name in [('saved-v2',n) for n,_ in STAGES.values()]+[
            ('rewrite-only','rewrite-bm25-w1'),('rewrite-only','rewrite-bm25-w03'),
            ('rewrite-bm25-w1','rewrite-bm25-w03')]:
        baseline={r['id']:r for r in datasets[reference]}
        changed=[]
        for row in datasets[name]:
            delta={metric:float(row[metric])-float(baseline[row['id']][metric])
                for metric in ('recall@5','hit@5','mrr@5','candidate_recall')}
            if any(abs(d)>1e-12 for d in delta.values()):
                changed.append({'id':row['id'],'type':row['type'],'delta':delta,
                    'before':{m:float(baseline[row['id']][m]) for m in delta},
                    'after':{m:float(row[m]) for m in delta}})
        paired[f'{name} vs {reference}']={'changed':changed,
            'counts':{m:{'wins':sum(r['delta'][m]>1e-12 for r in changed),
                         'losses':sum(r['delta'][m]<-1e-12 for r in changed),
                         'ties':64-sum(abs(r['delta'][m])>1e-12 for r in changed)}
                for m in ('recall@5','mrr@5','candidate_recall')}}
    save_json(out/'paired_changes.json',paired)
    header=['# Rewrite và BM25 — 64 câu','',
        'Chỉ chạy ba cấu hình được yêu cầu; v2 là kết quả đã lưu, không chạy lại baseline.','',
        '| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |',
        '|---|---:|---:|---:|---:|---:|']
    for name,m in summary.items():
        header.append(f'| {name} | {m["recall@5"]:.6f} | {m["hit@5"]:.6f} | {m["mrr@5"]:.6f} | {m["recall@20"]:.6f} | {m["multi_full_gold_top5"]}/27 |')
    header.extend(['','## Khối lượng xử lý','',
        '| Cấu hình | Cặp query–chunk qua Jev | Cặp thiếu cache Jev trong lượt chạy |',
        '|---|---:|---:|'])
    for name,m in summary.items():
        misses=m['jev_cache_misses'] if m['jev_cache_misses'] is not None else 'Không đo trong lượt này'
        header.append(f'| {name} | {m["candidate_chunks"]} | {misses} |')
    header.extend(['','64 lượt sinh rewrite được cache dùng chung; 62 câu thay đổi, 2 câu giữ gốc do kiểm tra đầu vào (d19, d32).',
        'Số cặp thiếu cache không bao gồm retry nội bộ của SDK và không phải hóa đơn API.','',
        '## Recall@5 tăng/giảm theo câu',''])
    for comparison,values in paired.items():
        if not comparison.endswith('vs saved-v2'): continue
        wins=[r['id'] for r in values['changed'] if r['delta']['recall@5']>1e-12]
        losses=[r['id'] for r in values['changed'] if r['delta']['recall@5']<-1e-12]
        header.append(f'- {comparison}: tăng {wins}; giảm {losses}.')
    header.extend(['','Dense/HyDE và câu con không thay đổi. Rewrite dùng cho Jev và nhánh BM25 của câu gốc.',
        'Trọng số RRF: Dense=1; BM25=1 hoặc 0.3. Giới hạn pool và Jev instructions giữ nguyên.',
        'API Jev dùng chung cache giữa các cấu hình; không dùng thời gian để so sánh tốc độ.',
        'Chỉ đánh giá retrieval, không đánh giá chất lượng trả lời; tập 64 câu đã được dùng để phát triển.'])
    (out/'comparison.md').write_text('\n'.join(header)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def verify(out):
    """Recompute all metrics/ranks and weighted pools from saved artifacts; no API."""
    import socket
    import sqlite3
    from rag.schema import Chunk

    def reject_network(*args,**kwargs):
        raise RuntimeError('Verification is offline')
    socket.create_connection=reject_network
    socket.socket.connect=reject_network
    meta=read_json(out/'config.json'); data=Path(meta['data_dir'])
    chunks={c.chunk_id:c for c in (Chunk.from_dict(json.loads(line)) for line in
        (data/'processed/chunks.jsonl').read_text(encoding='utf-8').splitlines() if line.strip())}
    questions={q.id:q for q in load_questions(QUESTIONS)}
    source={t['id']:t for t in read_json(SOURCE/'query_traces.json')}
    rewrites={r['id']:r for r in read_json(out/'rewrites.json')}
    db=sqlite3.connect((data/'cache/rerank.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    verified={}
    for stage,(name,weight) in STAGES.items():
        directory=out/name; traces=read_json(directory/'query_traces.json')
        with (directory/'retrieval_per_question.csv').open(encoding='utf-8-sig',newline='') as f:
            rows={r['id']:r for r in csv.DictReader(f)}
        assert len(traces)==len(rows)==64 and set(rows)==set(questions)
        for trace in traces:
            qid=trace['id']; q=questions[qid]; ids=trace['candidates']; row=rows[qid]
            assert trace['rewrite']==rewrites[qid]['rewrite']
            assert trace['rewrite_warning']==rewrites[qid]['error']
            assert trace['queries']==source[qid]['queries'] and not trace['errors']
            assert len(ids)==len(set(ids))
            if stage=='dense':
                assert ids==source[qid]['candidates']
            else:
                query_lists={}; original=[]
                # Each branch: raw arms -> weighted RRF -> 20 articles -> child top10.
                for index,query in enumerate(trace['queries']):
                    arms={arm:[Hit(cid,0,rank,arm) for rank,cid in enumerate(
                        trace['arms'].get(f'q{index}_{arm}' if len(trace['queries'])>1 else arm,[]),1)]
                        for arm in ('bm25','dense')}
                    assert all(arms.values()),qid
                    fused=rrf(arms,k=meta['rrf_k'],top_n=max(meta['rerank_n'],meta['arm_k'])*meta['article_pool_factor'],
                        weights={'bm25':weight})
                    branch=take_articles(fused,chunks,meta['rerank_n'])
                    if index==0: original=branch
                    selected=merge_by_article(branch,chunks)[:(meta['rerank_n'] if index==0 else meta['decomposition']['per_query_k'])]
                    selected_ids={cid for h in selected for cid in (h.chunk_id,*h.merged)}
                    query_lists[str(index)]=[h for h in branch if h.chunk_id in selected_ids]
                if len(trace['queries'])==1:
                    expected=original
                else:
                    fused=rrf(query_lists,k=meta['rrf_k'])
                    original_keys={article_key(chunks[h.chunk_id]) for h in original}
                    novel=[h for h in fused if article_key(chunks[h.chunk_id]) not in original_keys]
                    limit=min(meta['decomposition']['max_new_articles'],meta['decomposition']['pool_size']-len(original_keys))
                    extra=take_articles(novel,chunks,limit) if limit else []
                    expected=[*original,*extra]
                    assert not original_keys.intersection(article_key(chunks[h.chunk_id]) for h in extra)
                assert ids==[h.chunk_id for h in expected],qid
            assert len({article_key(chunks[cid]) for cid in ids})<=meta['decomposition']['pool_size']
            scored=[]
            for rank,cid in enumerate(ids,1):
                c=chunks[cid]
                key=ScoreCache.key('jev-1.13.0',trace['rewrite'],c,instructions=JEV_INSTRUCTIONS,
                    state=JevReranker.build_state(trace['rewrite'],c))
                score=db.execute('SELECT score FROM rerank_scores WHERE key=?',(key,)).fetchone()
                assert score is not None,(name,qid,cid)
                scored.append(Hit(cid,score[0],rank,'rerank'))
            ranked=merge_by_article(sorted(scored,key=lambda h:(-h.score,h.rank)),chunks)
            pool=[h.chunk_id for h in ranked]
            assert pool[:5]==trace['top5']==row['top5'].split()
            assert pool==[h['chunk_id'] for h in trace['ranked']]
            assert all(h.score==saved['score'] for h,saved in zip(ranked,trace['ranked']))
            for metric,fn,k in [('recall@5',recall_at_k,5),('hit@5',hit_at_k,5),('mrr@5',mrr_at_k,5),
                                ('recall@20',recall_at_k,20),('candidate_recall',recall_at_k,len(pool))]:
                assert abs(fn(q,pool,chunks,k)-float(row[metric]))<1e-12,(name,qid,metric)
        verified[name]={'questions':64,'all_ranks_and_metrics_recomputed':True,
            'same_decomposition_queries':True,'pool_verified_from_saved_weighted_arms':stage!='dense',
            'exact_frozen_source_pool':stage=='dense','all_jev_full_input_v2_scores_found':True}
    db.close()
    save_json(out/'verification.json',{'network_disabled':True,'baseline_execution':False,'stages':verified})
    print('Offline verification passed for all 192 question/config pairs.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['prepare',*STAGES,'report','verify'],required=True)
    ap.add_argument('--out',type=Path,default=DEFAULT_OUT)
    ap.add_argument('--resume',action='store_true',help='Continue a matching stage checkpoint; reuse cached scores')
    args=ap.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    if args.stage=='report':
        report(args.out); return
    if args.stage=='verify':
        verify(args.out); return
    s=replace(Settings.load(),decomp_enabled=True,query_rewrite_enabled=True,rewrite_for_rerank=True)
    assert s.advanced_methods==['hyde'] and s.rerank_backend=='jev'
    if args.stage=='prepare': prepare(s,args.out)
    else: run_stage(s,args.out,args.stage,resume=args.resume)


if __name__=='__main__':
    main()
