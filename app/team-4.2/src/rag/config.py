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

    # Embedding (TV3)
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536

    # LLM (TV4) — key/endpoint riêng nếu GPT 5.6 Lunar không dùng chung OpenAI
    llm_model: str = "gpt-5.6-lunar"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_temperature: float | None = 0.0   # None = không gửi tham số (một số model chỉ nhận mặc định)

    # Chunking (TV1)
    max_syllables: int = 300

    # Retrieval (TV2)
    arm_k: int = 20
    rrf_k: int = 60
    top_k: int = 5
    rerank_backend: str = "none"           # none | jev
    rerank_n: int = 20

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
        for name in ("embed_dim", "max_syllables", "arm_k", "top_k", "rerank_n",
                     "context_max_blocks", "context_max_words"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name.upper()} phải >= 1")
        if self.rrf_k < 0:
            raise ValueError("RRF_K phải >= 0")


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
