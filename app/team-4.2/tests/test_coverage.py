from dataclasses import replace

import pytest

from rag.config import Settings
from rag.retrieve.context import ContextConfig, select_context
from rag.retrieve.coverage import CoverageConfig, select_with_coverage
from rag.schema import Chunk, Hit


def fixture_data():
    chunks={cid:Chunk(cid,'law','law.txt',1,1,f'Điều {i}. Topic',cid)
            for i,cid in enumerate('abcdef',1)}
    ranked=[Hit(cid,score,i,'rerank') for i,(cid,score) in enumerate(
        zip('abcdef',[.95,.9,.8,.79,.78,.72]),1)]
    branches={'x':[Hit('a',1,1,'dense')],'y':[Hit('f',1,1,'dense')]}
    return chunks,ranked,branches


def test_marginal_coverage_promotes_complementary_evidence_and_preserves_scores():
    chunks,ranked,branches=fixture_data()
    original=list(ranked)
    selected=select_with_coverage(ranked,branches,chunks)
    assert [h.chunk_id for h in selected]==list('abfcde')
    assert ranked==original and selected[:2]==ranked[:2]
    assert {h.chunk_id:h.score for h in selected}=={h.chunk_id:h.score for h in ranked}
    assert [h.rank for h in selected]==list(range(1,7))
    # Production context selection sees exactly the same reordered evidence prefix.
    context=select_context(selected,chunks,ContextConfig(min_p=.5,max_blocks=5))
    assert context.chunk_ids==list('abfcd')


def test_low_quality_branch_hit_is_not_promoted_and_single_branch_is_unchanged():
    chunks,ranked,branches=fixture_data()
    ranked[-1]=replace(ranked[-1],score=.49)
    assert select_with_coverage(ranked,branches,chunks)==ranked
    ranked[-1]=replace(ranked[-1],score=.72)
    assert select_with_coverage(ranked,{'x':branches['x']},chunks)==ranked
    assert select_with_coverage(ranked,branches,chunks,config=CoverageConfig(weight=0))==ranked


def test_covered_branches_do_not_force_extra_slots_and_fallback_scores_are_ignored():
    chunks,ranked,branches=fixture_data()
    branches['y']=[Hit('a',1,1,'dense'),Hit('f',1,2,'dense')]
    assert select_with_coverage(ranked,branches,chunks)==ranked
    fallback=[replace(h,arm='fused') for h in ranked]
    assert select_with_coverage(fallback,branches,chunks)==fallback
    assert select_with_coverage(ranked,branches,chunks,k=2)==ranked


def test_coverage_validation_settings_and_duplicate_articles():
    settings=Settings.from_env({'COVERAGE_ENABLED':'true','COVERAGE_WEIGHT':'0.25'})
    assert settings.coverage_enabled and settings.coverage_weight==.25
    for invalid in [-1,2,float('nan'),float('inf')]:
        with pytest.raises(ValueError): CoverageConfig(weight=invalid)
        with pytest.raises(ValueError): Settings(coverage_min_p=invalid)
    chunks,ranked,branches=fixture_data()
    chunks['f']=replace(chunks['f'],section=chunks['a'].section)
    with pytest.raises(ValueError,match='one ranked hit per article'):
        select_with_coverage(ranked,branches,chunks)
