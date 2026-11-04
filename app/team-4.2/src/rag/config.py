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

    # Embedding (TV3) — chọn qua registry trong rag/index/embedders/registry.py.
    # Chỉ cần đổi EMBED_MODEL; dim/backend/tiền tố lấy theo registry. Mỗi model có vector index
    # riêng (indexes/vector/<model>/) nên không phải ingest lại — lần chạy đầu tự embed chunks.jsonl.
    embed_model: str = "jina-embeddings-v5-text-small"
    embed_dim: int | None = None             # None = theo registry (local: hỏi từ model)
    embed_backend: str = ""                  # "" = tự đoán: jina | openai | local | hash
    embed_query_prefix: str | None = None    # None = theo registry (vd. E5: "query: ")
    embed_passage_prefix: str | None = None
    embed_device: str = ""                   # local: "" = tự chọn (cuda nếu có), "cpu", "cuda"
    embed_batch_size: int = 32               # local
    jina_api_key: str | None = None

    # LLM (TV4) — key/endpoint riêng nếu LLM không dùng chung OpenAI
    llm_model: str = "gpt-6-luna"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_temperature: float | None = None  # None = không gửi tham số (gpt-6-luna chỉ nhận mặc định)

    # Chunking (TV1)
    max_syllables: int = 300

    # Retrieval (TV2)
    arm_k: int = 20
    rrf_k: int = 60
    top_k: int = 5
    rerank_backend: str = "none"           # none | jev | jina
    rerank_model: str = ""                 # rỗng = mặc định của backend (jev-1.13.0 / jina-reranker-v2-base-multilingual)
    rerank_n: int = 20
    # Arm của luồng chính (mode "hybrid"), vd. "dense" = bỏ BM25; rỗng = mọi arm đang bật.
    # Eval chọn arm riêng qua --configs nên không bị ảnh hưởng (trừ cấu hình "all").
    retrieval_arms: str = ""
    # Gộp nhiều chunk cùng một Điều thành một candidate trong top-k (retrieve/merge.py)
    merge_articles: bool = True
    # Khi gộp: mỗi arm lấy ARM_K * factor chunk, pool rerank = RERANK_N Điều khác nhau
    article_pool_factor: int = 2

    # Context (retrieve/context.py)
    context_min_p: float = 0.7
    context_max_blocks: int = 8
    context_max_words: int = 2400

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
    def retrieval_arm_list(self) -> list[str] | None:
        arms = list(dict.fromkeys(x.strip().lower() for x in self.retrieval_arms.split(",") if x.strip()))
        return arms or None

    @property
    def index_config_path(self) -> Path:
        return self.data_dir / "indexes" / "index_config.json"

    @property
    def chunks_path(self) -> Path:
        return self.data_dir / "processed" / "chunks.jsonl"

    @property
    def vector_dir(self) -> Path:
        """indexes/vector/<model>/. Index cũ build trước khi tách theo model (meta.json ngay tại
        indexes/vector/) vẫn được dùng nếu đúng model đang chọn."""
        import json

        from rag.index.embedders.registry import model_slug

        root = self.data_dir / "indexes" / "vector"
        legacy_meta = root / "meta.json"
        if legacy_meta.is_file():
            try:
                if json.loads(legacy_meta.read_text(encoding="utf-8")).get("embed_model") == self.embed_model:
                    return root
            except (OSError, ValueError):
                pass
        return root / model_slug(self.embed_model)

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
        if self.rerank_backend not in ("none", "jev", "jina"):
            raise ValueError(f"RERANK_BACKEND phải là none | jev | jina, nhận {self.rerank_backend!r}")
        if self.embed_dim is not None and self.embed_dim < 1:
            raise ValueError("EMBED_DIM phải >= 1")
        for name in ("embed_batch_size", "max_syllables", "arm_k", "top_k", "rerank_n", "article_pool_factor",
                     "context_max_blocks", "context_max_words"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name.upper()} phải >= 1")
        if self.rrf_k < 0:
            raise ValueError("RRF_K phải >= 0")


def _convert(name: str, raw: str, default: Any) -> Any:
    if name == "data_dir":
        return Path(raw)
    if name == "embed_dim":
        return None if raw.strip().lower() in {"none", "null", "auto"} else int(raw)
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
