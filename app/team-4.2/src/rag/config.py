"""Cấu hình chung — TV5.

Đọc từ biến môi trường, có thể nạp thêm file `.env` (không ghi đè biến đã có sẵn).
Dùng thư viện chuẩn thay vì pydantic-settings: ít phụ thuộc, đủ cho vài chục tham số.

    settings = Settings.load()                 # tìm app/team-4.2/.env rồi .env ở thư mục hiện tại
    settings = Settings.load(env_file=None)    # chỉ đọc biến môi trường (dùng trong test)

Mọi đường dẫn tính từ thư mục chạy lệnh (gốc repo).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
import math
from typing import Any

DEFAULT_ENV_FILES = (Path("app/team-4.2/.env"), Path(".env"))


def parse_env_file(path: Path) -> dict[str, str]:
    """Đọc file .env dạng KEY=VALUE; bỏ dòng trống, comment `#`, comment cuối dòng và dấu nháy."""
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if value[:1] in {'"', "'"} and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        out[key] = value
    return out


def load_env_file(path: Path | str) -> dict[str, str]:
    """Nạp .env vào os.environ, KHÔNG ghi đè biến đã có. Trả các biến đã nạp."""
    loaded = {}
    for key, value in parse_env_file(Path(path)).items():
        if key not in os.environ:
            os.environ[key] = value
            loaded[key] = value
    return loaded


@dataclass(frozen=True)
class Settings:
    # Đường dẫn
    data_dir: Path = Path("data/team-4.2")

    # Embedding (TV3): "jina-*" dùng Jina API (cần JINA_API_KEY), còn lại dùng OpenAI.
    # Đổi model/dim thì phải index lại (DATA_DIR mới hoặc xoá indexes/).
    embed_model: str = "jina-embeddings-v5-text-small"
    embed_dim: int = 1024
    jina_api_key: str | None = None

    # LLM (TV4) — key/endpoint riêng nếu LLM không dùng chung OpenAI
    llm_model: str = "gpt-6-luna"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_temperature: float | None = None  # None = không gửi tham số (gpt-6-luna chỉ nhận mặc định)
    condense_model: str = "gpt-4o-mini"   # Model nhẹ cho QueryCondenser gộp ngữ cảnh chat nhanh

    # OCR (W02-02c): "none" | "gemini". Gemini gửi ẢNH ra ngoài (OpenRouter -> Google) trước khi
    # mask PII -> chỉ bật cho tài liệu công khai. Tesseract local làm tín hiệu chất lượng.
    ocr_engine: str = "none"
    ocr_model: str = "google/gemini-3.5-flash-lite"
    openrouter_api_key: str | None = None       # OPENROUTER_API_KEY (hoặc "openrouter=" trong .env cũ)
    ocr_cost_cap_usd: float = 1.0               # dừng OCR khi tổng chi phí trong cache/ocr vượt ngưỡng
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    ocr_min_confidence: float = 65.0            # chọn trên split dev của fixtures

    # Chunking (TV1)
    max_syllables: int = 300

    # Retrieval (TV2)
    arm_k: int = 20
    rrf_k: int = 60
    bm25_rrf_weight: float = 1.0
    query_rewrite_enabled: bool = False
    rewrite_for_rerank: bool = True       # false: rewrite for BM25 only; Jev sees original
    top_k: int = 5
    rerank_backend: str = "none"           # none | jev
    rerank_n: int = 20
    # Gộp nhiều chunk cùng một Điều thành một candidate trong top-k (retrieve/merge.py)
    merge_articles: bool = True
    # Khi gộp: mỗi arm lấy ARM_K * factor chunk, pool rerank = RERANK_N Điều khác nhau
    article_pool_factor: int = 2

    # Query decomposition: runtime only; independent of HyDE and retrieval mode.
    decomp_enabled: bool = False
    decomp_max_subqueries: int = 3
    decomp_include_original: bool = True
    decomp_per_query_k: int = 10
    decomp_pool_size: int = 30
    decomp_max_new_articles: int = 10

    # Optional post-Jev evidence selection; no additional model calls.
    coverage_enabled: bool = False
    coverage_anchor_k: int = 2
    coverage_min_p: float = 0.5
    coverage_weight: float = 0.25
    coverage_branch_k: int = 5

    listwise_enabled: bool = False
    listwise_model: str = "gpt-6-luna"
    listwise_candidate_n: int = 10
    listwise_margin: float = 0.05
    listwise_min_p: float = 0.5
    listwise_excerpt_words: int = 300

    # Context (retrieve/context.py)
    context_min_p: float = 0.4
    context_max_blocks: int = 10
    context_max_words: int = 2800

    # Opt-in Think agent; these do not change the baseline RAG path.
    agent_max_rounds: int = 3
    agent_max_searches: int = 8
    agent_initial_subqueries: int = 3
    agent_followup_searches: int = 2
    agent_candidates_per_search: int = 10
    agent_initial_pool_size: int = 30
    agent_new_units_per_round: int = 10
    agent_max_units: int = 50
    agent_max_xref_depth: int = 2
    agent_xrefs_per_round: int = 6
    agent_max_xref_targets: int = 12
    agent_max_requirements: int = 8
    agent_max_model_calls: int = 24
    agent_max_service_requests: int = 240
    agent_max_model_bytes: int = 600000
    agent_max_input_chars: int = 60000
    agent_max_output_tokens: int = 3000
    agent_deadline_s: float = 180.0
    agent_retrieval_mode: str = "dense"

    # Phương pháp nâng cao (src/rag/advanced/), vd. "hyde,contextual"; rỗng = baseline
    advanced: str = ""
    # Checkpoint cho ADVANCED=splade / colbert (mặc định là bản tiếng Anh — đổi sang đa ngữ/tiếng Việt)
    splade_model: str = "naver/splade-cocondenser-ensembledistil"
    colbert_model: str = "colbert-ir/colbertv2.0"

    # --- đường dẫn suy ra ---------------------------------------------------

    @property
    def advanced_methods(self) -> list[str]:
        return list(dict.fromkeys(x.strip().lower() for x in self.advanced.split(",") if x.strip()))

    @property
    def index_config_path(self) -> Path:
        return self.data_dir / "indexes" / "index_config.json"

    @property
    def chunks_path(self) -> Path:
        return self.data_dir / "processed" / "chunks.jsonl"

    @property
    def vector_dir(self) -> Path:
        return self.data_dir / "indexes" / "vector"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    # --- nạp ------------------------------------------------------------------

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Đọc từ `env` (mặc định os.environ). Tên biến = tên trường viết HOA."""
        env = os.environ if env is None else env
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            raw = env.get(f.name.upper())
            if raw is None or raw == "":
                continue
            kwargs[f.name] = _convert(f.name, raw, getattr(cls, f.name))
        if "openrouter_api_key" not in kwargs:
            legacy = {k.strip().lower(): v for k, v in env.items()}.get("openrouter")
            if legacy:
                kwargs["openrouter_api_key"] = legacy
        if kwargs.get("ocr_engine", "none").lower() not in {"none", "gemini"}:
            raise ValueError(f"OCR_ENGINE phải là none|gemini, nhận {kwargs['ocr_engine']!r}")
        return cls(**kwargs)

    @classmethod
    def load(cls, env_file: Path | str | None | tuple = DEFAULT_ENV_FILES) -> Settings:
        if env_file is not None:
            candidates = env_file if isinstance(env_file, tuple) else (env_file,)
            for path in candidates:
                if Path(path).is_file():
                    load_env_file(path)
                    break
        return cls.from_env()

    def __post_init__(self) -> None:
        if self.rerank_backend not in ("none", "jev"):
            raise ValueError(f"RERANK_BACKEND phải là none | jev, nhận {self.rerank_backend!r}")
        for name in ("embed_dim", "max_syllables", "arm_k", "top_k", "rerank_n", "article_pool_factor",
                     "context_max_blocks", "context_max_words", "decomp_max_subqueries",
                     "decomp_per_query_k", "decomp_pool_size"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name.upper()} phải >= 1")
        if self.rrf_k < 0:
            raise ValueError("RRF_K phải >= 0")
        if not math.isfinite(self.bm25_rrf_weight) or self.bm25_rrf_weight < 0:
            raise ValueError('BM25_RRF_WEIGHT must be finite and nonnegative')
        if self.decomp_max_new_articles < 0:
            raise ValueError("DECOMP_MAX_NEW_ARTICLES phải >= 0")
        if self.coverage_anchor_k < 0 or self.coverage_branch_k < 1:
            raise ValueError('Invalid coverage anchor/branch limits')
        if any(not math.isfinite(v) or not 0<=v<=1
               for v in (self.coverage_min_p,self.coverage_weight)):
            raise ValueError('Coverage probabilities/weight must be finite and in [0,1]')
        if self.coverage_enabled and self.listwise_enabled:
            raise ValueError('Enable coverage or listwise selection separately')
        if not 8<=self.listwise_candidate_n<=12 or self.listwise_excerpt_words<1:
            raise ValueError('Invalid listwise shortlist/excerpt limits')
        if any(not math.isfinite(v) or not 0<=v<=1 for v in (self.listwise_margin,self.listwise_min_p)):
            raise ValueError('Listwise thresholds must be finite and in [0,1]')


def _convert(name: str, raw: str, default: Any) -> Any:
    if name == "data_dir":
        return Path(raw)
    if name == "llm_temperature":
        return None if raw.strip().lower() in {"none", "null", "default"} else float(raw)
    if isinstance(default, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


__all__ = ["Settings", "load_env_file", "parse_env_file"]
