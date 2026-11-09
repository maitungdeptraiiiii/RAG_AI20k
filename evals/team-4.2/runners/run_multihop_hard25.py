"""Benchmark current configured retrieval, including retrieval-side LLMs; forbid answer generation.

Usage (PowerShell, repo root):
  $env:PYTHONPATH='app/team-4.2/src'; $env:PYTHONIOENCODING='utf-8'
  python evals/team-4.2/runners/run_multihop_hard25.py
"""
import argparse
import csv
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from difflib import SequenceMatcher
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace

from rag.config import Settings
from rag.eval.metrics import load_questions, unmatched_gold, recall_at_k, hit_at_k, mrr_at_k
from rag.eval.runner import write_csv, summary_markdown
from rag.generate.llm import OpenAIChatLLM, LLMCache
from rag.pipeline import RAGPipeline

BASE = Path('evals/team-4.2')
DATASET = BASE / 'datasets/benchmark_multihop_hard25.jsonl'
OLD = BASE / 'datasets/benchmark_doi_thuong.jsonl'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def forbidden(*args, **kwargs):
    raise AssertionError('Answer generation is forbidden in this benchmark')


class CountedLLM(OpenAIChatLLM):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests = 0
        self.logical_calls = 0
        self.cache_hits = 0

    def complete(self, system, user):
        self.logical_calls += 1
        key = LLMCache.key(self.model_id, self.temperature,
                           [{'role':'system','content':system},{'role':'user','content':user}])
        if self.cache and self.cache.get(key) is not None:
            self.cache_hits += 1
        return super().complete(system, user)

    def _get_client(self):
        client = super()._get_client()
        def create(**kwargs):
            self.requests += 1
            return client.chat.completions.create(**kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def audit(questions, chunks, out):
    raw = [json.loads(x) for x in DATASET.read_text(encoding='utf-8').splitlines()]
    old = load_questions(OLD)
    def tokens(s):
        return set(re.findall(r'\w+', s.lower()))
    def sim(a,b):
        a,b=tokens(a),tokens(b)
        return len(a&b)/len(a|b)
    nearest=[]
    for r,q in zip(raw,questions):
        assert q.type=='multi' and len(q.gold)>=3 and len({g.source for g in q.gold})>=2
        assert len(r['reasoning_steps'])==len(q.gold)
        expected=[c.chunk_id for c in chunks if q.is_relevant(c)]
        assert set(expected)==set(r['gold_chunk_ids'])
        for e,g in zip(r['evidence'],q.gold):
            matches=[c for c in chunks if g.matches(c)]
            assert e['text']=='\n\n'.join(c.text for c in matches)
        match=max(old,key=lambda x:sim(q.question,x.question))
        nearest.append({'id':q.id,'nearest_old_id':match.id,'word_jaccard':sim(q.question,match.question),
                        'sequence_ratio':SequenceMatcher(None,q.question,match.question).ratio(),
                        'new_topic':r['topic'], 'old_question':match.question})
        assert q.question not in {x.question for x in old}
        assert {(g.source,g.section) for g in q.gold} not in [
            {(g.source,g.section) for g in x.gold} for x in old]
    bad=unmatched_gold(questions,chunks)
    assert not bad,bad
    pairs=[{'a':a.id,'b':b.id,'word_jaccard':sim(a.question,b.question)}
           for i,a in enumerate(questions) for b in questions[i+1:]]
    result={'n':len(questions),'old_n':len(old),'unmatched_gold':bad,
            'gold_count_distribution':dict(Counter(len(q.gold) for q in questions)),
            'cross_source_count':sum(len({g.source for g in q.gold})>=2 for q in questions),
            'exact_question_duplicates':0,'identical_old_gold_sets':0,
            'nearest_old':nearest,'top_internal_pairs':sorted(pairs,key=lambda x:x['word_jaccard'],reverse=True)[:10],
            'method':'Exact text/gold-set checks + lexical screens + authored topic/fact-pattern review. Similarity is not proof of semantic independence.',
            'review_status':'Corpus-grounded author review; no independent legal expert sign-off.'}
    save(out/'quality_audit.json',result)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',default=str(BASE/'results/multihop-hard25-current-20261106'))
    ap.add_argument('--audit-only',action='store_true')
    ap.add_argument('--resume',action='store_true')
    ap.add_argument('--no-hyde',action='store_true',help='disable HyDE')
    args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    s=Settings.load()
    if args.no_hyde:
        from dataclasses import replace
        adv=[m for m in s.advanced_methods if m!='hyde']
        s=replace(s,advanced=','.join(adv) if adv else '')
    from rag.index.store import ChunkStore
    chunks=ChunkStore(s.chunks_path).all()
    qs=load_questions(DATASET)
    assert len(qs)==25 and s.top_k==5
    quality=audit(qs,chunks,out)
    if args.audit_only:
        print(json.dumps({k:v for k,v in quality.items() if k not in ['nearest_old','top_internal_pairs']},ensure_ascii=False))
        return
    assert args.resume or not (out/'config.json').exists(),'Choose a fresh output directory'
    old_before=sha(OLD)
    config={k:v for k,v in asdict(s).items() if not any(x in k for x in ['key','base_url'])}
    config.update({'questions_sha256':sha(DATASET),'old_questions_sha256':old_before,
                   'chunks_sha256':sha(s.chunks_path),'index_signature':json.loads(s.index_config_path.read_text()),
                   'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                   'started_at':datetime.now().astimezone().isoformat(),'mode':'hybrid (all enabled arms, current settings)',
                   'answer_generation':False,'python':__import__('sys').version,
                   'versions':{n:importlib.metadata.version(n) for n in ['openai','qdrant-client','pyvi','typesafe-sdk']}})
    if args.resume:
        saved=json.loads((out/'config.json').read_text(encoding='utf-8'))
        for key in config:
            if key not in ['started_at','versions','python']:
                assert str(saved[key])==str(config[key]),('Resume configuration changed',key)
    else:
        save(out/'config.json',config)
    # Construction retains configured HyDE, decomposition, rewrite and listwise.
    # No ask/context/generation entry point is ever invoked.
    RAGPipeline.ask=forbidden
    RAGPipeline.ask_debug=forbidden
    import rag.pipeline as pipeline_module
    pipeline_module.answer_question=forbidden
    llm=CountedLLM(s.llm_model,temperature=s.llm_temperature,base_url=s.llm_base_url,
                  api_key=s.llm_api_key,cache=LLMCache(s.cache_dir/'llm.sqlite'))
    p=RAGPipeline.from_settings(s,llm=llm)
    # Strict benchmark failure handling only: never score silent HyDE/JeV fallbacks.
    if 'hyde' in s.advanced_methods:
        p.retriever.arms['dense'].fallback=False
    rows=[]; traces=[]
    prior={'retrieval_llm_logical_calls':0,'retrieval_llm_cache_hits':0,'retrieval_llm_sdk_requests':0}
    if args.resume and (out/'retrieval_per_question.csv').exists():
        with (out/'retrieval_per_question.csv').open(encoding='utf-8',newline='') as f:
            rows=list(csv.DictReader(f))
        for r in rows:
            for k in list(r):
                if '@' in k or k=='elapsed_s':r[k]=float(r[k])
        traces=json.loads((out/'query_traces.json').read_text(encoding='utf-8'))
        prior=json.loads((out/'call_counts.json').read_text(encoding='utf-8'))
        assert [r['id'] for r in rows]==[t['id'] for t in traces]==[q.id for q in qs[:len(rows)]]
    completed=len(rows)
    for i,q in enumerate(qs,1):
        if i<=completed:continue
        start=time.perf_counter()
        res=p.retriever.retrieve(q.question,s.top_k,mode='hybrid',rerank=True)
        if res.errors or (s.rerank_backend!='none' and not res.reranked):
            save(out/'failed_attempt.json',{'id':q.id,'errors':res.errors,'reranked':res.reranked})
            raise RuntimeError(f'{q.id}: retrieval failed; successful checkpoints preserved; use --resume')
        top=[h.chunk_id for h in res.hits]; pool=[h.chunk_id for h in res.ranked]
        def covered(hits,g):
            return any(g.matches(p.retriever.chunks[cid]) for h in hits for cid in (h.chunk_id,*h.merged))
        missing5=[j for j,g in enumerate(q.gold) if not covered(res.hits,g)]
        missing20=[j for j,g in enumerate(q.gold) if not covered(res.ranked[:20],g)]
        row={'id':q.id,'type':q.type,'author':q.author,'config':'current-retrieval',
             'recall@5':recall_at_k(q,top,p.retriever.chunks,5),
             'hit@5':hit_at_k(q,top,p.retriever.chunks,5),'mrr@5':mrr_at_k(q,top,p.retriever.chunks,5),
             'recall@20':recall_at_k(q,pool,p.retriever.chunks,20),
             'all_gold@5':float(not missing5),'all_gold@20':float(not missing20),
             'merged_recall@5':1-len(missing5)/len(q.gold),'merged_recall@20':1-len(missing20)/len(q.gold),
             'reranked':res.reranked,'query_count':len(res.queries) or 1,
             'elapsed_s':round(time.perf_counter()-start,3),'top5':' '.join(top),
             'errors':json.dumps(res.errors,ensure_ascii=False)}
        rows.append(row)
        traces.append({'id':q.id,'question':q.question,'queries':res.queries,'errors':res.errors,
                       'missing_gold_top5':missing5,'missing_gold_top20':missing20,
                       'candidates':[asdict(h) for h in res.candidates],
                       'ranked':[asdict(h) for h in res.ranked],
                       'pre_selection_ranked':[asdict(h) for h in res.pre_selection_ranked],
                       'selection_policy':res.selection_policy,'listwise_metadata':res.listwise_metadata,
                       'top5_articles':[p.retriever.chunks[h.chunk_id].section for h in res.hits]})
        write_csv(rows,out/'retrieval_per_question.csv'); save(out/'query_traces.json',traces)
        save(out/'call_counts.json',{'retrieval_llm_logical_calls':prior['retrieval_llm_logical_calls']+llm.logical_calls,
             'retrieval_llm_cache_hits':prior['retrieval_llm_cache_hits']+llm.cache_hits,
             'retrieval_llm_sdk_requests':prior['retrieval_llm_sdk_requests']+llm.requests})
        print(f'[{i}/25] {q.id} recall5={row["recall@5"]:.3f} errors={res.errors}',flush=True)
    metrics={k:sum(r[k] for r in rows)/len(rows) for k in
             ['recall@5','hit@5','mrr@5','recall@20','all_gold@5','all_gold@20','merged_recall@5','merged_recall@20']}
    stats={'status':'complete','n':len(rows),'metrics':metrics,
           'questions_with_errors':sum(bool(t['errors']) for t in traces),
           'error_types':dict(Counter(k for t in traces for k in t['errors'])),
           **json.loads((out/'call_counts.json').read_text()),'answer_generation_calls':0,
           'old_dataset_unchanged':sha(OLD)==old_before,
           'elapsed_s_sum':sum(r['elapsed_s'] for r in rows)}
    assert stats['old_dataset_unchanged']
    save(out/'metrics.json',stats)
    (out/'summary.md').write_text('# Multi-hop hard25 — retrieval only\n\n'+summary_markdown(rows)+
         '\n```json\n'+json.dumps(stats,ensure_ascii=False,indent=2)+'\n```\n',encoding='utf-8')
    print(json.dumps(stats,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()
