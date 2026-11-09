import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.advanced.rewrite import QueryRewriter
from rag.config import Settings
from rag.retrieve.fusion import rrf
from rag.retrieve.hybrid import HybridRetriever
from rag.schema import Chunk, Hit


@pytest.mark.parametrize('reply', ['oops', '{"query":""}', '{"query":42}',
    '{"query":"tuoi 19"}', '{"query":"Điều 18 tuoi 18"}', '{"query":"tuoi 18","extra":1}'])
def test_bad_rewrite_preserves_original_and_reports_error(reply):
    rewriter=QueryRewriter(SimpleNamespace(complete=lambda *args:reply))
    result=rewriter.rewrite('tuoi 18')
    assert result.query=='tuoi 18' and result.error


def test_weighted_rrf_changes_relative_influence_and_zero_excludes_arm():
    ranked={'bm25':[Hit('a',1,1,'bm25')],'dense':[Hit('b',1,1,'dense')]}
    equal=rrf(ranked)
    weighted=rrf(ranked,weights={'bm25':.3})
    assert [h.chunk_id for h in equal]==['a','b']
    assert [h.chunk_id for h in weighted]==['b','a']
    assert weighted[1].score==pytest.approx(.3/61)
    assert [h.chunk_id for h in rrf(ranked,weights={'bm25':0})]==['b']
    for weight in (-1,float('nan'),float('inf')):
        with pytest.raises(ValueError): rrf(ranked,weights={'bm25':weight})
        with pytest.raises(ValueError): Settings(bm25_rrf_weight=weight)
    s=Settings.from_env({'QUERY_REWRITE_ENABLED':'true','BM25_RRF_WEIGHT':'0.3'})
    assert s.query_rewrite_enabled and s.bm25_rrf_weight==.3


def test_benchmark_cache_only_clients_fail_on_miss_instead_of_calling_api(tmp_path):
    from rag.generate.llm import LLMCache
    from rag.index.embedder import EmbeddingCache

    path=Path(__file__).resolve().parents[3]/'evals/team-4.2/runners/run_rewrite_benchmark.py'
    spec=importlib.util.spec_from_file_location('rewrite_benchmark',path)
    runner=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    settings=Settings(data_dir=tmp_path)
    llm=runner.CacheOnlyLLM(settings)
    with pytest.raises(RuntimeError,match='cache miss'): llm.complete('system','query')
    key=LLMCache.key(settings.llm_model,settings.llm_temperature,
        [{'role':'system','content':'system'},{'role':'user','content':'query'}])
    llm.cache.put(key,'cached')
    assert llm.complete('system','query')=='cached'
    embedder=runner.CacheOnlyEmbedder(settings)
    with pytest.raises(RuntimeError,match='cache miss'): embedder.embed_query(['query'])
    key=EmbeddingCache.key(settings.embed_model+'#retrieval.query','query')
    embedder.cache.put_many({key:[1.,0.]})
    assert embedder.embed_query(['query'])==[[1.,0.]]
    with pytest.raises(RuntimeError,match='forbidden'): embedder.embed(['query'])
    llm.cache.close(); embedder.cache.close()


def test_checkpoint_write_retries_without_truncating_previous_json(tmp_path,monkeypatch):
    path=Path(__file__).resolve().parents[3]/'evals/team-4.2/runners/run_rewrite_benchmark.py'
    spec=importlib.util.spec_from_file_location('rewrite_checkpoint',path)
    runner=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    target=tmp_path/'checkpoint.json'
    target.write_text('{"old":true}',encoding='utf-8')
    replace_original=Path.replace
    attempts=[]
    def flaky_replace(source,destination):
        attempts.append(1)
        assert json.loads(target.read_text(encoding='utf-8'))=={'old':True}
        if len(attempts)==1: raise OSError(22,'transient file error')
        return replace_original(source,destination)
    monkeypatch.setattr(Path,'replace',flaky_replace)
    monkeypatch.setattr(runner.time,'sleep',lambda seconds:None)
    runner.save_json(target,{'new':True})
    assert len(attempts)==2 and json.loads(target.read_text(encoding='utf-8'))=={'new':True}


@pytest.mark.parametrize('decomposed', [False,True])
@pytest.mark.parametrize('rewrite_for_rerank', [False,True])
def test_rewrite_only_changes_rerank_and_original_bm25_not_dense_or_subqueries(decomposed,rewrite_for_rerank):
    calls=[]
    class Arm:
        def __init__(self,name): self.name=name
        def build(self,chunks): pass
        def search(self,query,k):
            calls.append((self.name,query))
            return [Hit('d:0000',1,1,self.name)]
    class Ranker:
        def rerank(self,query,hits,chunks,k):
            calls.append(('rank',query))
            return [Hit(h.chunk_id,.9,i,'rerank') for i,h in enumerate(hits,1)]
    r=HybridRetriever(Arm('bm25'),Arm('dense'),reranker=Ranker(),rewrite_for_rerank=rewrite_for_rerank)
    r.build([Chunk('d:0000','d','law',1,1,None,'text')])
    r.rewriter=QueryRewriter(SimpleNamespace(complete=lambda *args:json.dumps({'query':'rewritten'})))
    if decomposed:
        r.decomposer=SimpleNamespace(plan=lambda q:SimpleNamespace(queries=[q,'sub1','sub2']),
            include_original=True,per_query_k=10,pool_size=30,max_new_articles=10)
    result=r.retrieve('original')
    assert ('bm25','rewritten') in calls and ('dense','original') in calls
    assert ('bm25','original') not in calls and ('dense','rewritten') not in calls
    assert [c for c in calls if c[0]=='rank']==[('rank','rewritten' if rewrite_for_rerank else 'original')]
    assert result.query=='original' and result.rerank_query==('rewritten' if rewrite_for_rerank else None)
    if decomposed:
        assert ('bm25','sub1') in calls and ('dense','sub2') in calls
    if not rewrite_for_rerank:
        def reject_rewrite(*args): raise AssertionError('Dense must not call rewrite')
        r.rewriter=SimpleNamespace(rewrite=reject_rewrite)
        dense_result=r.retrieve('original',mode='dense')
        assert dense_result.query=='original' and dense_result.rerank_query is None
