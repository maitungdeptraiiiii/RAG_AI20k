"""Select a compact evidence set using Jev quality and marginal subquery coverage.

Branch retrieval ranks are a proxy for coverage, not a semantic entailment score.
The selector never calls a model, adds candidates, or changes Jev probabilities.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import math

from rag.retrieve.merge import article_key, merge_by_article
from rag.schema import Chunk, Hit


@dataclass(frozen=True)
class CoverageConfig:
    anchor_k: int = 2
    min_p: float = 0.5
    weight: float = 0.25
    branch_k: int = 5

    def __post_init__(self) -> None:
        if self.anchor_k < 0 or self.branch_k < 1:
            raise ValueError('Coverage anchor_k must be >=0; branch_k must be >=1')
        if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (self.min_p,self.weight)):
            raise ValueError('Coverage min_p and weight must be finite and in [0,1]')


def select_with_coverage(
    ranked: Sequence[Hit], branches: Mapping[str,Sequence[Hit]],
    chunks: Mapping[str,Chunk], *, k: int = 5, config: CoverageConfig | None = None,
) -> list[Hit]:
    """Return selected top-k followed by the original-order tail.

    For branch article rank r<=B, support=(B+1-r)/B; otherwise support=0.
    Objective=(1-weight)*Jev_p + weight*mean_j(max(0,support_j-current_best_j)).
    Anchors keep their exact positions. Promotion requires Jev_p>=min_p.
    If no eligible choice exists, fill from the original order. No per-branch quota.
    Original Jev scores, arms and merged IDs are preserved; Hit.rank follows selection.
    """
    cfg=config or CoverageConfig()
    if k < 1:
        raise ValueError('k must be >=1')
    original=list(ranked)
    if not original or cfg.weight==0 or k<=cfg.anchor_k:
        return original
    if any(h.arm!='rerank' or not 0<=h.score<=1 for h in original):
        return original  # RRF/fallback scores must never be interpreted as probabilities.
    keys={h.chunk_id:article_key(chunks[h.chunk_id]) for h in original}
    if len(set(keys.values()))!=len(original):
        raise ValueError('Coverage expects one ranked hit per article')
    support=[]
    for hits in branches.values():
        if not hits:
            continue
        articles=merge_by_article(hits,chunks)[:cfg.branch_k]
        support.append({article_key(chunks[h.chunk_id]):
                        (cfg.branch_k+1-rank)/cfg.branch_k
                        for rank,h in enumerate(articles,1)})
    if len(support)<2:
        return original
    limit=min(k,len(original))
    selected=original[:min(cfg.anchor_k,limit)]
    selected_ids={h.chunk_id for h in selected}
    best=[max((s.get(keys[h.chunk_id],0.) for h in selected),default=0.) for s in support]
    positions={h.chunk_id:i for i,h in enumerate(original)}
    while len(selected)<limit:
        remaining=[h for h in original if h.chunk_id not in selected_ids]
        eligible=[h for h in remaining if h.score>=cfg.min_p]
        def objective(hit: Hit) -> tuple[float,int]:
            gain=sum(max(0.,s.get(keys[hit.chunk_id],0.)-covered)
                     for s,covered in zip(support,best))/len(support)
            return ((1-cfg.weight)*hit.score+cfg.weight*gain,-positions[hit.chunk_id])
        chosen=max(eligible,key=objective) if eligible else remaining[0]
        selected.append(chosen); selected_ids.add(chosen.chunk_id)
        best=[max(covered,s.get(keys[chosen.chunk_id],0.)) for s,covered in zip(support,best)]
    ordered=[*selected,*(h for h in original if h.chunk_id not in selected_ids)]
    return [replace(h,rank=rank) for rank,h in enumerate(ordered,1)]
