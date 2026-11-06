import json
from dataclasses import replace

import pytest

from rag.config import Settings
from rag.retrieve.listwise import LISTWISE_SYSTEM, ListwiseConfig, ListwiseSelector
from rag.schema import Chunk, Hit


class FakeLLM:
    def __init__(self,reply=None): self.reply=reply; self.calls=[]
    def complete(self,system,user):
        self.calls.append((system,json.loads(user)))
        if isinstance(self.reply,Exception): raise self.reply
        return self.reply


def inputs():
    chunks={f'd:{i:04d}':Chunk(f'd:{i:04d}','d','law.txt',1,1,f'Điều {i}. Title','legal text')
            for i in range(10)}
    ranked=[Hit(cid,.95-i*.025,i+1,'rerank') for i,cid in enumerate(chunks)]
    return chunks,ranked


def test_valid_selection_uses_one_call_preserves_probabilities_and_original_tail():
    chunks,ranked=inputs(); llm=FakeLLM(); selector=ListwiseSelector(llm)
    plan=selector.prepare('original',['original','need1','need2'],ranked,chunks)
    assert plan.triggered and len(plan.candidates)==10
    chosen=list(plan.candidates)[-5:]
    llm.reply=json.dumps({'selected_ids':chosen})
    result=selector.select(plan)
    ids=[plan.candidates[cid].chunk_id for cid in chosen]
    assert len(llm.calls)==1 and llm.calls[0][0]==LISTWISE_SYSTEM
    assert [h.chunk_id for h in result.ranked[:5]]==ids
    assert [h.chunk_id for h in result.ranked[5:]]==[h.chunk_id for h in ranked if h.chunk_id not in ids]
    assert {(h.chunk_id,h.score,h.merged) for h in result.ranked}=={(h.chunk_id,h.score,h.merged) for h in ranked}
    assert llm.calls[0][1]['subqueries']==['need1','need2']
    assert all(set(c)=={'id','source','section','text','truncated'} for c in llm.calls[0][1]['candidates'])
    assert not result.metadata['error']


@pytest.mark.parametrize('reply',[
    'not json','{"selected_ids":["C01"]}',
    '{"selected_ids":["C01","C02","C03","C04","unknown"]}',
    '{"selected_ids":["C01","C02","C03","C04","C04"]}',
    '{"selected_ids":["C01","C02","C03","C04",5]}',
    '{"selected_ids":["C01","C02","C03","C04","C05"],"answer":"extra"}',
    ConnectionError('no connection')])
def test_invalid_response_or_api_error_falls_back_once_without_repair(reply):
    chunks,ranked=inputs(); llm=FakeLLM(reply)
    result=ListwiseSelector(llm).rerank('q',['need1','need2'],ranked,chunks)
    assert result.ranked==ranked and result.metadata['error'] and len(llm.calls)==1


def test_gate_skips_single_intent_clear_margin_low_quality_and_non_jev():
    chunks,ranked=inputs(); llm=FakeLLM(); selector=ListwiseSelector(llm)
    assert not selector.prepare('q',['q','need'],ranked,chunks).triggered
    clear=[replace(h,score=(.95 if i<5 else .7-i*.01)) for i,h in enumerate(ranked)]
    assert selector.prepare('q',['a','b'],clear,chunks).reason=='clear_cutoff'
    low=[replace(h,score=.45-i*.01) for i,h in enumerate(ranked)]
    assert selector.prepare('q',['a','b'],low,chunks).reason=='few_eligible_candidates'
    fallback=[replace(h,arm='fused') for h in ranked]
    assert selector.prepare('q',['a','b'],fallback,chunks).reason=='not_jev'
    assert llm.calls==[]


def test_deterministic_payload_clipping_and_config_validation():
    chunks,ranked=inputs()
    chunks={cid:replace(c,text='one two three four') for cid,c in chunks.items()}
    selector=ListwiseSelector(FakeLLM(),ListwiseConfig(excerpt_words=2))
    a=selector.prepare('q',['x','y'],ranked,chunks)
    b=selector.prepare('q',['x','y'],ranked,chunks)
    assert a.payload==b.payload and a.payload_sha256==b.payload_sha256
    assert all(c['truncated'] and c['text']=='one two' for c in json.loads(a.payload)['candidates'])
    for n in (7,13):
        with pytest.raises(ValueError): ListwiseConfig(candidate_n=n)
    for threshold in (-1,2,float('nan'),float('inf')):
        with pytest.raises(ValueError): ListwiseConfig(margin=threshold)
    with pytest.raises(ValueError): Settings(listwise_enabled=True,coverage_enabled=True)
    assert Settings.from_env({'LISTWISE_ENABLED':'true'}).listwise_enabled
