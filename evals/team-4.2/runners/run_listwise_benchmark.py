"""One gated listwise configuration over frozen v2 retrieval/Jev scores.

prepare: offline gate, deterministic requests, cache/token estimates; no model calls.
run: only listwise LLM cache misses may call the configured API, one attempt per query.
verify: offline replay of cached responses, all pools/scores/metrics; no API fallback.
"""
from __future__ import annotations

import argparse
from collections import Counter
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
from rag.eval.metrics import load_questions
from rag.generate.llm import LLMCache, OpenAIChatLLM
from rag.retrieve.context import ContextConfig
from rag.retrieve.hybrid import HybridRetriever
from rag.retrieve.listwise import LISTWISE_SYSTEM, ListwiseConfig, ListwiseSelector
from rag.retrieve.merge import merge_by_article
from rag.retrieve.rerank import DEFAULT_JEV_MODEL, JEV_INSTRUCTIONS, SCORE_CACHE_SCHEMA
from rag.schema import Chunk, Hit
from run_coverage_benchmark_offline import CachedJev, SavedDense, ForbiddenBM25, metrics, context_stats
from run_rewrite_benchmark import save_json, save_csv, summarize

SOURCE=Path('evals/team-4.2/results/doi-thuong-64q-scenario-decomp-v2')
BRANCH_SOURCE=Path('evals/team-4.2/results/doi-thuong-64q-rewrite-bm25-v1/rewrite-bm25-w03')
COVERAGE=Path('evals/team-4.2/results/doi-thuong-64q-coverage-v1')
QUESTIONS=Path('evals/team-4.2/datasets/benchmark_doi_thuong.jsonl')
OUT=Path('evals/team-4.2/results/doi-thuong-64q-listwise-v1')
POLICY=ListwiseConfig(candidate_n=10,margin=.05,min_p=.5,excerpt_words=300)


def read_json(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rows_at(directory):
    with (directory/'retrieval_per_question.csv').open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))
def reject_network(*args,**kwargs): raise RuntimeError('This stage forbids network access')
def block_network():
    socket.create_connection=reject_network
    socket.socket.connect=reject_network
    socket.socket.connect_ex=reject_network


class NoLLM:
    def complete(self,*args): raise AssertionError('Preflight cannot call an LLM')


class CacheOnlyLLM:
    def __init__(self,settings,data):
        self.settings=settings
        self.db=sqlite3.connect((data/'cache/llm.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    def complete(self,system,user):
        key=LLMCache.key(self.settings.llm_model,self.settings.llm_temperature,
            [{'role':'system','content':system},{'role':'user','content':user}])
        row=self.db.execute('SELECT text FROM completions WHERE key=?',(key,)).fetchone()
        if row is None: raise RuntimeError('Listwise response missing from cache; no API fallback')
        return row[0]


class MeteredCompletions:
    def __init__(self,completions):
        self.inner=completions; self.calls=0; self.last_usage=None; self.usage=[]
    def create(self,**kwargs):
        self.calls+=1; self.last_usage=None
        response=self.inner.create(**kwargs)
        u=getattr(response,'usage',None)
        self.last_usage=({name:getattr(u,name,None) for name in
            ('prompt_tokens','completion_tokens','total_tokens')} if u is not None else None)
        self.usage.append(self.last_usage)
        return response


def collect():
    settings=Settings.load(); metadata=read_json(SOURCE/'config.json')
    assert metadata['questions_sha256']==sha(QUESTIONS)
    assert metadata['rerank_model']==DEFAULT_JEV_MODEL
    assert metadata['rerank_instructions_sha256']==hashlib.sha256(JEV_INSTRUCTIONS.encode()).hexdigest()
    data=Path(metadata['data_dir']); chunk_path=data/'processed/chunks.jsonl'
    assert sha(chunk_path)==metadata['index_snapshot']['chunks_sha256']
    chunks={c.chunk_id:c for c in (Chunk.from_dict(json.loads(line)) for line in
        chunk_path.read_text(encoding='utf-8').splitlines() if line.strip())}
    questions=load_questions(QUESTIONS)
    source={t['id']:t for t in read_json(SOURCE/'query_traces.json')}
    raw={t['id']:t for t in read_json(BRANCH_SOURCE/'query_traces.json')}
    reference={r['id']:r for r in rows_at(SOURCE)}
    assert len(questions)==len(source)==len(reference)==64
    ranker=CachedJev(data); ranked={}; dense_hits={}; plans={}
    for q in questions:
        t=source[q.id]; assert t['queries']==raw[q.id]['queries'] and not t['errors']
        hits=[Hit(cid,0.,i,'fused') for i,cid in enumerate(t['candidates'],1)]
        ranked[q.id]=merge_by_article(ranker.rerank(q.question,hits,chunks,len(hits)),chunks)
        assert [h.chunk_id for h in ranked[q.id][:5]]==t['top5']
        for metric,value in metrics(q,ranked[q.id],chunks).items():
            assert abs(value-float(reference[q.id][metric]))<1e-12
        plans[q.question]=t['queries']
        for i,query in enumerate(t['queries']):
            ids=raw[q.id]['arms']['dense' if len(t['queries'])==1 else f'q{i}_dense']
            if query in dense_hits: assert dense_hits[query]==ids
            dense_hits[query]=ids
    score_hash=hashlib.sha256(json.dumps(sorted(ranker.scores.items())).encode()).hexdigest()
    ranker.db.close()
    context=ContextConfig(min_p=settings.context_min_p,max_blocks=settings.context_max_blocks,
        max_words=settings.context_max_words,fixed_k=metadata['top_k'])
    provenance={'source':str(SOURCE),'source_config_sha256':sha(SOURCE/'config.json'),
        'source_traces_sha256':sha(SOURCE/'query_traces.json'),'source_csv_sha256':sha(SOURCE/'retrieval_per_question.csv'),
        'branch_traces_sha256':sha(BRANCH_SOURCE/'query_traces.json'),'coverage_csv_sha256':sha(COVERAGE/'retrieval_per_question.csv'),
        'questions_sha256':sha(QUESTIONS),'chunks_sha256':sha(chunk_path),'score_cache_snapshot_sha256':score_hash,
        'listwise_config':asdict(POLICY),'listwise_system_prompt':LISTWISE_SYSTEM,
        'prompt_sha256':hashlib.sha256(LISTWISE_SYSTEM.encode()).hexdigest(),
        'selector_code_sha256':sha(Path('app/team-4.2/src/rag/retrieve/listwise.py')),
        'llm':settings.llm_model,'llm_temperature':settings.llm_temperature,
        'rerank_model':DEFAULT_JEV_MODEL,'score_cache_schema':SCORE_CACHE_SCHEMA,
        'context_config':asdict(context),'new_jev_calls':0,'baseline_execution':False,
        'live_retrieval_execution':False,'hyde_execution':False,'embedding_execution':False,
        'rewrite_execution':False,'parameter_sweep':False,'policy_frozen_before_evaluation':True,
        'api_attempts_per_eligible_query':1,'transport_retries':0}
    return settings,metadata,data,chunks,questions,source,ranked,dense_hits,plans,context,provenance


def prepare(out):
    block_network()
    settings,meta,data,chunks,questions,source,ranked,dense_hits,plans,context,provenance=collect()
    assert not out.exists(),'Use a fresh output; do not overwrite previous plans'
    selector=ListwiseSelector(NoLLM(),POLICY)
    cache=CacheOnlyLLM(settings,data)
    records=[]
    try:
        import tiktoken
        encoding=tiktoken.get_encoding('o200k_base')
    except Exception:
        encoding=None
    for q in questions:
        p=selector.prepare(q.question,source[q.id]['queries'],ranked[q.id],chunks,k=meta['top_k'])
        cached=False
        if p.triggered:
            try: cache.complete(LISTWISE_SYSTEM,p.payload); cached=True
            except RuntimeError: pass
        records.append({'id':q.id,'question':q.question,'triggered':p.triggered,'reason':p.reason,
            'payload_sha256':p.payload_sha256,'payload':p.payload,
            'candidate_chunk_ids':{cid:h.chunk_id for cid,h in p.candidates.items()},
            'response_cached':cached,'input_characters':len(LISTWISE_SYSTEM)+len(p.payload) if p.triggered else 0,
            'input_whitespace_units':len(LISTWISE_SYSTEM.split())+len(p.payload.split()) if p.triggered else 0,
            'estimated_input_tokens':(len(encoding.encode(LISTWISE_SYSTEM))+len(encoding.encode(p.payload))+12
                                      if p.triggered and encoding is not None else None)})
    cache.db.close()
    out.mkdir(parents=True)
    save_json(out/'config.json',provenance)
    save_json(out/'plans.json',records)
    gate={'questions':64,'triggered':sum(r['triggered'] for r in records),
        'new_api_requests_at_most':sum(r['triggered'] and not r['response_cached'] for r in records),
        'gate_reasons':dict(Counter(r['reason'] for r in records)),
        'input_characters':sum(r['input_characters'] for r in records),
        'input_whitespace_units':sum(r['input_whitespace_units'] for r in records),
        'estimated_input_tokens':(sum(r['estimated_input_tokens'] or 0 for r in records) if encoding is not None else None),
        'token_estimate_encoding':'o200k_base, provider tokenizer and chat framing may differ' if encoding else 'unavailable offline',
        'model_api_calls':0}
    save_json(out/'preflight.json',gate)
    print(json.dumps(gate,indent=2),flush=True)


def build_retriever(meta,data,chunks,dense_hits,plans,selector):
    dense=SavedDense(dense_hits); ranker=CachedJev(data)
    r=HybridRetriever(ForbiddenBM25(),dense,reranker=ranker,listwise=selector,
        arm_k=meta['arm_k'],rrf_k=meta['rrf_k'],rerank_n=meta['rerank_n'],
        merge_articles=meta['merge_articles'],article_pool_factor=meta['article_pool_factor'])
    r.decomposer=SimpleNamespace(**meta['decomposition'],plan=lambda q:DecompositionPlan(list(plans[q])))
    r.build(chunks.values())
    return r


def run(out,*,resume=False):
    settings,meta,data,chunks,questions,source,original,dense_hits,plans,context,provenance=collect()
    assert read_json(out/'config.json')==provenance,'Frozen preflight inputs changed'
    prepared={p['id']:p for p in read_json(out/'plans.json')}
    assert len(prepared)==64
    if not resume:
        assert not (out/'retrieval_per_question.csv').exists(),'Use --resume for matching checkpoints'
    from openai import OpenAI
    kwargs={key:value for key,value in [('base_url',settings.llm_base_url),('api_key',settings.llm_api_key)] if value}
    client=OpenAI(**kwargs,max_retries=0,timeout=90)
    meter=MeteredCompletions(client.chat.completions)
    tracked=SimpleNamespace(chat=SimpleNamespace(completions=meter))
    llm=OpenAIChatLLM(settings.llm_model,temperature=settings.llm_temperature,
        cache=LLMCache(data/'cache/llm.sqlite'),client=tracked,max_retries=0)
    selector=ListwiseSelector(llm,POLICY)
    retriever=build_retriever(meta,data,chunks,dense_hits,plans,selector)
    rows=[]; details=[]; orphan={}
    if resume:
        rows=rows_at(out); details=read_json(out/'query_traces.json')
        common=min(len(rows),len(details)); orphan={r['id']:r for r in rows[common:]}
        assert [r['id'] for r in rows[:common]]==[t['id'] for t in details[:common]]==[q.id for q in questions[:common]]
        rows=rows[:common]; details=details[:common]
    completed=len(rows)
    for i,q in enumerate(questions,1):
        if i<=completed: continue
        meter.last_usage=None; calls_before=meter.calls
        result=retriever.retrieve(q.question,meta['top_k'],mode='dense')
        m=result.listwise_metadata; p=prepared[q.id]
        assert m['triggered']==p['triggered'] and m['payload_sha256']==p['payload_sha256']
        assert [h.chunk_id for h in result.candidates]==source[q.id]['candidates']
        assert {(h.chunk_id,h.score,h.merged) for h in result.ranked}=={(h.chunk_id,h.score,h.merged) for h in original[q.id]}
        assert result.queries==source[q.id]['queries'] and result.reranked
        assert not result.errors or set(result.errors)=={'listwise'}
        assert meter.calls-calls_before<=1
        measured=metrics(q,result.ranked,chunks)
        assert measured['candidate_recall']==metrics(q,original[q.id],chunks)['candidate_recall']
        request_count=meter.calls-calls_before+int(orphan.get(q.id,{}).get('listwise_api_requests',0))
        rows.append({'id':q.id,'type':q.type,'author':q.author,'config':'v2+listwise-v1',**measured,
            'reranked':True,'errors':json.dumps(result.errors,ensure_ascii=False),
            'query_count':len(result.queries),'candidate_chunks':len(result.candidates),
            'selection_policy':result.selection_policy,'listwise_triggered':m['triggered'],
            'listwise_api_requests':request_count,'listwise_fallback':bool(m['error']),
            'top5':' '.join(h.chunk_id for h in result.hits),'jev_cache_misses':0})
        details.append({'id':q.id,'question':q.question,'queries':result.queries,
            'candidates':[h.chunk_id for h in result.candidates],'listwise_metadata':m,
            'selection_policy':result.selection_policy,'errors':result.errors,
            'usage':meter.last_usage,'api_requests':request_count,
            'ranked':[{'chunk_id':h.chunk_id,'score':h.score,'rank':h.rank,'merged':list(h.merged)} for h in result.ranked],
            'context_before':context_stats(q,original[q.id],chunks,context),
            'context_after':context_stats(q,result.ranked,chunks,context)})
        save_csv(out/'retrieval_per_question.csv',rows)
        save_json(out/'query_traces.json',details)
        print(f'[{i}/64] {q.id}: call={meter.calls-calls_before}, R5={measured["recall@5"]:.3f}, fallback={bool(m["error"])}',flush=True)
        if m['error'] and m['error'].startswith(('AuthenticationError','PermissionDeniedError')):
            raise RuntimeError('API authentication failed; stopped after first failure, checkpoints retained')
    retriever.reranker.db.close(); llm.cache.close(); client.close()
    assert len(rows)==64
    print(json.dumps(summarize(rows),indent=2),flush=True)


def verify(out):
    block_network()
    settings,meta,data,chunks,questions,source,original,dense_hits,plans,context,provenance=collect()
    assert read_json(out/'config.json')==provenance
    prepared={p['id']:p for p in read_json(out/'plans.json')}
    details=read_json(out/'query_traces.json'); rows=rows_at(out)
    assert len(details)==len(rows)==64
    cached=CacheOnlyLLM(settings,data); selector=ListwiseSelector(cached,POLICY)
    for q,t,row in zip(questions,details,rows):
        assert q.id==t['id']==row['id']
        plan=selector.prepare(q.question,source[q.id]['queries'],original[q.id],chunks,k=meta['top_k'])
        assert plan.payload_sha256==prepared[q.id]['payload_sha256']
        decision=selector.select(plan,k=meta['top_k'])
        assert decision.metadata==t['listwise_metadata']
        assert [h.chunk_id for h in decision.ranked]==[h['chunk_id'] for h in t['ranked']]
        assert all(h.score==saved['score'] and list(h.merged)==saved['merged'] for h,saved in zip(decision.ranked,t['ranked']))
        assert t['candidates']==source[q.id]['candidates'] and t['queries']==source[q.id]['queries']
        assert row['top5'].split()==[h.chunk_id for h in decision.ranked[:meta['top_k']]]
        for metric,value in metrics(q,decision.ranked,chunks).items():
            assert abs(value-float(row[metric]))<1e-12
        assert t['context_after']==context_stats(q,decision.ranked,chunks,context)
    cached.db.close()
    save_json(out/'verification.json',{'questions':64,'all_pools_scores_merged_ids_preserved':True,
        'all_gates_and_shortlists_match_preflight':True,'all_selections_replayed_from_llm_cache':True,
        'all_metrics_and_context_recomputed':True,'network_forbidden':True,'new_model_api_calls':0,
        'baseline_execution':False,'parameter_sweep':False})
    print('Offline verification passed for all 64 questions.')


def report(out):
    block_network()
    datasets={'saved-v2':rows_at(SOURCE),'coverage-v1':rows_at(COVERAGE),'listwise-v1':rows_at(out)}
    summaries={name:summarize(rows) for name,rows in datasets.items()}
    details=read_json(out/'query_traces.json')
    calls={'gated_questions':sum(t['listwise_metadata']['triggered'] for t in details),
        'api_requests':sum(t['api_requests'] for t in details),
        'fallbacks':sum(bool(t['listwise_metadata']['error']) for t in details),
        'usage_reported_requests':sum(t['usage'] is not None for t in details),
        'reported_prompt_tokens':sum((t['usage'] or {}).get('prompt_tokens') or 0 for t in details),
        'reported_completion_tokens':sum((t['usage'] or {}).get('completion_tokens') or 0 for t in details)}
    save_json(out/'summary.json',summaries); save_json(out/'api_usage.json',calls)
    save_json(out/'summary_by_type.json',{kind:{name:summarize([r for r in rows if r['type']==kind])
        for name,rows in datasets.items()} for kind in ('multi','paraphrase')})
    paired={}
    for name,old in datasets.items():
        if name=='listwise-v1': continue
        old={r['id']:r for r in old}; changes=[]
        for row in datasets['listwise-v1']:
            delta={m:float(row[m])-float(old[row['id']][m]) for m in ('recall@5','hit@5','mrr@5','candidate_recall')}
            if any(abs(v)>1e-12 for v in delta.values()):
                changes.append({'id':row['id'],'type':row['type'],'delta':delta,
                    'before':{m:float(old[row['id']][m]) for m in delta},
                    'after':{m:float(row[m]) for m in delta}})
        paired[name]={'changed':changes,'counts':{m:{
            'wins':sum(c['delta'][m]>1e-12 for c in changes),
            'losses':sum(c['delta'][m]<-1e-12 for c in changes),
            'ties':64-sum(abs(c['delta'][m])>1e-12 for c in changes)} for m in ('recall@5','mrr@5')}}
    save_json(out/'paired_changes.json',paired)
    ctx={stage:{'empty':sum(t[f'context_{stage}']['empty'] for t in details),
        'full_gold':sum(t[f'context_{stage}']['full_gold'] for t in details),
        'mean_blocks':sum(t[f'context_{stage}']['blocks'] for t in details)/64,
        'mean_whitespace_units':sum(t[f'context_{stage}']['whitespace_units'] for t in details)/64}
        for stage in ('before','after')}
    save_json(out/'context_summary.json',ctx)
    lines=['# Gated listwise v1 — benchmark chính 64 câu','',
        'Chỉ chạy một cấu hình mới trên pool/điểm Jev v2 đã lưu. Không chạy lại baseline hoặc retrieval.',
        'Gate và prompt cố định ở preflight; không điều chỉnh theo gold sau khi xem kết quả.','',
        '| Cấu hình | Recall@5 | Hit@5 | MRR@5 | Recall@20 | Multi đủ gold |',
        '|---|---:|---:|---:|---:|---:|']
    for name,m in summaries.items():
        lines.append(f'| {name} | {m["recall@5"]:.6f} | {m["hit@5"]:.6f} | {m["mrr@5"]:.6f} | {m["recall@20"]:.6f} | {m["multi_full_gold_top5"]}/27 |')
    lines.extend(['',f'API/usage: {calls}',f'Context simulation: {ctx}',
        'Giữ xác suất Jev gốc sau selection. Chỉ xếp lại ứng viên, không thêm Điều ngoài pool/shortlist.',
        'Model chỉ thấy đoạn đại diện, không bảo đảm toàn bộ nội dung Điều; excerpt và gate có giới hạn.',
        'Đây là đánh giá retrieval và mô phỏng context, chưa đánh giá câu trả lời hoặc tập độc lập.',
        'Thời gian và số request có ảnh hưởng cache; số token lấy từ usage provider nếu có.'])
    (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'summary':summaries,'calls':calls,'context':ctx},indent=2))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage',choices=['prepare','run','verify','report'],required=True)
    ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--resume',action='store_true')
    args=ap.parse_args()
    if args.stage=='prepare': prepare(args.out)
    elif args.stage=='run': run(args.out,resume=args.resume)
    elif args.stage=='verify': verify(args.out)
    else: report(args.out)


if __name__=='__main__': main()
