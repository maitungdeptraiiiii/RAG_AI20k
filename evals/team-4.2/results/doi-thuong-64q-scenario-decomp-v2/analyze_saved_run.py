"""Verify and compare saved benchmark artifacts offline; never executes a benchmark."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import socket
import sqlite3
import sys

sys.path.insert(0, str(Path('app/team-4.2/src').resolve()))
from rag.eval.metrics import load_questions, recall_at_k, hit_at_k, mrr_at_k
from rag.retrieve.merge import article_key, merge_by_article
from rag.retrieve.rerank import ScoreCache, JevReranker
from rag.schema import Chunk, Hit


def reject_network(*args, **kwargs):
    raise RuntimeError('This analysis is offline; network forbidden')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_rows(directory):
    with (directory / 'retrieval_per_question.csv').open(encoding='utf-8-sig', newline='') as f:
        return {r['id']: r for r in csv.DictReader(f)}


def main():
    socket.create_connection = reject_network
    socket.socket.connect = reject_network
    root = Path(__file__).resolve().parent
    previous = root.parent / 'doi-thuong-64q-decomposition-anchor20-add10-jev-partial'
    base = root.parent / 'doi-thuong-64q-decomposition'
    new, old = read_rows(root), read_rows(previous)
    config, old_config = read_json(root/'config.json'), read_json(previous/'config.json')
    questions = {q.id: q for q in load_questions('evals/team-4.2/datasets/benchmark_doi_thuong.jsonl')}
    assert len(new) == len(old) == len(questions) == 64
    assert set(new) == set(old) == set(questions)
    fields = ('questions_sha256', 'index_signature', 'index_snapshot', 'advanced', 'llm',
              'rerank', 'rerank_model', 'rerank_instructions_sha256', 'score_cache_schema',
              'arm_k', 'rerank_n', 'article_pool_factor', 'merge_articles', 'top_k', 'rrf_k',
              'pool_strategy', 'decomposition')
    assert all(config[k] == old_config[k] for k in fields)
    assert config['prompt_sha256'] != old_config['prompt_sha256']
    assert not config['baseline_execution']
    data = Path(config['data_dir'])
    chunks = {c.chunk_id: c for c in (Chunk.from_dict(json.loads(line)) for line in
              (data/'processed/chunks.jsonl').read_text(encoding='utf-8').splitlines() if line.strip())}
    traces = read_json(root/'query_traces.json')
    plans = {r['id']: r for r in read_json(root/'decomposition_plans.json')['records']}
    originals = {r['id']: r for r in read_json(base/'query_traces.json') if r['config']=='hyde+jev'}
    db = sqlite3.connect((data/'cache/rerank.sqlite').resolve().as_uri()+'?mode=ro', uri=True)
    checks, gold_changes, rank_details = [], [], []
    for t in traces:
        qid = t['id']; q = questions[qid]; row = new[qid]
        assert row['reranked']=='True' and json.loads(row['errors'])=={}
        assert t['queries']==plans[qid]['queries'] and t['queries'][0]==q.question
        original = originals[qid]['candidates']
        assert t['candidates'][:len(original)]==original, qid
        original_keys={article_key(chunks[c]) for c in original}
        extra_keys={article_key(chunks[c]) for c in t['candidates'][len(original):]}
        assert not extra_keys.intersection(original_keys) and len(extra_keys)<=10
        assert len(original_keys | extra_keys)<=30
        scored=[]
        for i,cid in enumerate(t['candidates'],1):
            c=chunks[cid]
            key=ScoreCache.key(config['rerank_model'],q.question,c,
                instructions=config['rerank_instructions'],state=JevReranker.build_state(q.question,c))
            result=db.execute('SELECT score FROM rerank_scores WHERE key=?',(key,)).fetchone()
            assert result is not None,(qid,cid)
            scored.append(Hit(cid,result[0],i,'rerank'))
        ranked=merge_by_article(sorted(scored,key=lambda h:(-h.score,h.rank)),chunks)
        pool=[h.chunk_id for h in ranked]
        rank_details.append({'id':qid,'gold_ranks':[
            {'source':g.source,'section':g.section,
             'rank':next((i for i,cid in enumerate(pool,1) if g.matches(chunks[cid])),None)}
            for g in q.gold], 'ranked':[
                {'rank':i,'chunk_id':h.chunk_id,'score':h.score,'section':chunks[h.chunk_id].section,
                 'gold':q.is_relevant(chunks[h.chunk_id])} for i,h in enumerate(ranked,1)]})
        assert pool[:5]==t['top5']==row['top5'].split(),qid
        for metric,fn,k in [('recall@5',recall_at_k,5),('hit@5',hit_at_k,5),
                            ('mrr@5',mrr_at_k,5),('recall@20',recall_at_k,20),
                            ('candidate_recall',recall_at_k,len(pool))]:
            assert abs(fn(q,pool,chunks,k)-float(row[metric]))<1e-12,(qid,metric)
        checks.append({'id':qid,'original_articles':len(original_keys),'extra_articles':len(extra_keys),
                       'candidate_chunks':len(scored),'full_gold_top5':float(row['recall@5'])==1})
        delta={m:float(row[m])-float(old[qid][m]) for m in ('recall@5','mrr@5','candidate_recall')}
        if any(abs(v)>1e-12 for v in delta.values()):
            gold_changes.append({'id':qid,'question':q.question,'delta':delta,
                'before':{m:float(old[qid][m]) for m in delta},'after':{m:float(row[m]) for m in delta}})
    db.close()
    def stats(rows,kind=None):
        selected=[r for r in rows.values() if kind is None or r['type']==kind]
        return {'questions':len(selected),**{m:sum(float(r[m]) for r in selected)/len(selected)
            for m in ('recall@5','hit@5','mrr@5','recall@20','candidate_recall')},
            'full_gold_top5':sum(float(r['recall@5'])==1 for r in selected),
            'decomposed':sum(int(r['query_count'])>1 for r in selected),
            'total_queries':sum(int(r['query_count']) for r in selected),
            'candidate_chunks':sum(int(r['candidate_chunks']) for r in selected)}
    result={'verification':{'rows':64,'all_reranked':True,'no_errors':True,
        'all_original_candidates_preserved_in_order':True,'extra_articles_at_most_10':True,
        'all_metrics_recomputed_from_full_input_v2_score_cache':True,
        'all_query_plans_reused_exactly':True,'unchanged_config_fields':list(fields),
        'baseline_execution':False,'network_disabled_for_analysis':True},
        'previous':{k:stats(old,None if k=='all' else k) for k in ('all','multi','paraphrase')},
        'new':{k:stats(new,None if k=='all' else k) for k in ('all','multi','paraphrase')},
        'changes':gold_changes,'pool_checks':checks}
    (root/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'rank_and_context_analysis.json').write_text(json.dumps({
        'verification':'Replayed every rank from full-input-v2 score cache, offline',
        'context_analysis':None,'note':'Context and answer quality were not evaluated in this analysis.',
        'per_question':rank_details},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('verification','previous','new')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
