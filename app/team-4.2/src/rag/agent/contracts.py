"""Request-local state and hard logical budgets for the multi-hop runtime."""

from __future__ import annotations

import json
import math
import time
import hashlib
from dataclasses import dataclass, field, fields
from typing import Any
from threading import Lock

from rag.generate.llm import BoundedCompletion
from rag.schema import Chunk, Hit, LLM


@dataclass(frozen=True)
class AgentConfig:
    max_rounds: int = 3
    max_searches: int = 8
    initial_subqueries: int = 3
    followup_searches: int = 2
    candidates_per_search: int = 10
    initial_pool_size: int = 30
    new_units_per_round: int = 10
    max_units: int = 50
    max_xref_depth: int = 2
    xrefs_per_round: int = 6
    max_xref_targets: int = 12
    max_requirements: int = 8
    max_model_calls: int = 24
    max_service_requests: int = 240
    max_model_bytes: int = 600_000
    max_input_chars: int = 60_000
    max_output_tokens: int = 3000
    deadline_s: float = 180.0
    retrieval_mode: str = "dense"

    def __post_init__(self):
        optional_limits = {"initial_subqueries", "followup_searches", "max_xref_depth",
                           "xrefs_per_round", "max_xref_targets"}
        for item in fields(self):
            value = getattr(self, item.name)
            minimum = 0 if item.name in optional_limits else 1
            if isinstance(item.default, int) and (type(value) is not int or value < minimum):
                raise ValueError(f"Agent {item.name} must be an integer >= {minimum}")
        if self.max_model_calls < 6:
            raise ValueError("Agent needs at least six model calls, including finalization reserve")
        if (isinstance(self.deadline_s, bool) or not isinstance(self.deadline_s, (int, float)) or
            not math.isfinite(self.deadline_s) or self.deadline_s <= 0):
            raise ValueError("Agent deadline must be finite and positive")
        if self.retrieval_mode not in {"dense", "hybrid", "bm25"}:
            raise ValueError("Agent retrieval mode must be dense, hybrid or bm25")

    @classmethod
    def from_settings(cls, settings):
        return cls(**{f.name: getattr(settings, f"agent_{f.name}", f.default) for f in fields(cls)})


class BudgetExceeded(RuntimeError):
    pass


class OutputError(ValueError):
    pass


@dataclass
class Budget:
    config: AgentConfig
    started: float = field(default_factory=time.monotonic)
    model_calls: int = 0
    model_bytes: int = 0
    searches: int = 0
    xref_targets: int = 0
    rounds: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hits: int = 0
    provider_requests: int = 0
    calls: list[dict[str, Any]] = field(default_factory=list)
    service_requests: dict[str, int] = field(default_factory=dict)
    _lock: Any = field(default_factory=Lock, repr=False)

    def check(self):
        if time.monotonic() - self.started >= self.config.deadline_s:
            raise BudgetExceeded("deadline_exceeded")

    def can_finalize_after_search(self) -> bool:
        return self.model_calls + 5 <= self.config.max_model_calls

    def remaining_s(self):
        self.check()
        return max(0.01, self.config.deadline_s - (time.monotonic() - self.started))

    def charge_service(self, category):
        self.check()
        with self._lock:
            if sum(self.service_requests.values()) >= self.config.max_service_requests:
                raise BudgetExceeded("service_request_limit")
            self.service_requests[category] = self.service_requests.get(category, 0) + 1

    def summary(self):
        return {
            "rounds": self.rounds, "searches": self.searches, "xref_targets": self.xref_targets,
            "model_calls": self.model_calls, "model_bytes": self.model_bytes,
            "provider_requests": self.provider_requests, "cache_hits": self.cache_hits,
            "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
            "elapsed_s": round(time.monotonic() - self.started, 3),
            "calls": list(self.calls),
            "service_requests": dict(self.service_requests),
        }


class ModelGateway:
    """All agent LLM roles (including HyDE/condense) share this ledger.

    Byte admission conservatively reserves four bytes per output token. Reported
    token usage is measured when the backend supplies it, not invented for fakes.
    Embedding/reranker SDK attempts are not counted as LLM provider requests.
    """

    def __init__(self, llm: LLM, budget: Budget, stage: str = "hyde"):
        self.llm, self.budget, self.stage = llm, budget, stage
        self.model_id = llm.model_id

    def complete(self, system: str, user: str) -> str:
        return self.call(self.stage, system, user)

    def call(self, stage: str, system: str, user: str, *, reserve_calls: int = 4) -> str:
        b, c = self.budget, self.budget.config
        b.check()
        if b.model_calls + 1 + reserve_calls > c.max_model_calls:
            raise BudgetExceeded("model_call_limit")
        if len(system) + len(user) > c.max_input_chars:
            raise BudgetExceeded("model_input_limit")
        input_bytes = len((system + user).encode("utf-8"))
        allowance = input_bytes + c.max_output_tokens * 4
        final_reserve = c.max_model_bytes // 3 if reserve_calls >= 4 else 0
        if b.model_bytes + allowance + final_reserve > c.max_model_bytes:
            raise BudgetExceeded("model_byte_limit")
        b.model_calls += 1
        b.model_bytes += allowance
        record = {"stage": stage, "model": self.model_id, "status": "started",
                  "prompt_sha256": hashlib.sha256(system.encode("utf-8")).hexdigest(),
                  "input_sha256": hashlib.sha256(user.encode("utf-8")).hexdigest()}
        b.calls.append(record)
        try:
            bounded = getattr(self.llm, "complete_bounded", None)
            # An attempted provider call is still a request if it raises.
            b.provider_requests += 1
            if bounded is not None:
                remaining = c.deadline_s - (time.monotonic() - b.started)
                result = bounded(system, user, timeout_s=max(0.01, remaining), max_output_tokens=c.max_output_tokens)
            else:
                # Test/custom backends implement the existing LLM protocol.
                result = BoundedCompletion(self.llm.complete(system, user))
            if not isinstance(result.text, str) or len(result.text.encode("utf-8")) > c.max_output_tokens * 4:
                raise OutputError("Model output exceeded the bounded contract")
            b.model_bytes -= c.max_output_tokens * 4 - len(result.text.encode("utf-8"))
            b.cache_hits += int(result.cache_hit)
            b.provider_requests -= int(result.cache_hit)
            b.input_tokens += result.input_tokens
            b.output_tokens += result.output_tokens
            record.update(status="ok", cache_hit=result.cache_hit)
            b.check()
            return result.text
        except Exception as exc:
            record.update(status="error", error=type(exc).__name__)
            raise

    def json(self, stage: str, system: str, payload: dict, *, reserve_calls: int = 4) -> dict:
        raw = self.call(stage, system, json.dumps(payload, ensure_ascii=False), reserve_calls=reserve_calls)
        try:
            data = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise OutputError(f"Invalid JSON at {stage}") from exc
        if not isinstance(data, dict):
            raise OutputError(f"Expected an object at {stage}")
        return data


@dataclass(frozen=True)
class Requirement:
    id: str
    question: str
    depends_on: tuple[str, ...] = ()


@dataclass
class Evidence:
    id: str
    key: tuple[str, ...]
    chunk: Chunk
    chunk_ids: tuple[str, ...]
    round: int
    depth: int
    origins: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Assessment:
    requirement_id: str
    status: str
    evidence_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class Claim:
    text: str
    evidence_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]


@dataclass
class RunState:
    requirements: list[Requirement] = field(default_factory=list)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    by_unit: dict[tuple[str, ...], str] = field(default_factory=dict)
    assessments: list[Assessment] = field(default_factory=list)
    searched: set[str] = field(default_factory=set)
    followed: set[str] = field(default_factory=set)
    hits: list[Hit] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
