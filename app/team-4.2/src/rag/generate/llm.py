"""LLM client — TV4.

GPT 5.6 Lunar qua SDK `openai` (Chat Completions), cache SQLite theo sha256(model, messages)
để chạy lại eval không tốn tiền và kết quả tất định. Retry khi rate limit / timeout / lỗi kết nối.

Nếu GPT 5.6 Lunar dùng endpoint/key riêng (OpenAI-compatible), truyền `base_url` / `api_key`
(LLM_BASE_URL / LLM_API_KEY); không thì SDK tự đọc OPENAI_API_KEY.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from rag.schema import LLM

log = logging.getLogger(__name__)


class LLMCache:
    def __init__(self, path: Path | str = ":memory:") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS completions (key TEXT PRIMARY KEY, text TEXT NOT NULL)"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def key(model_id: str, temperature: float | None, messages: Sequence[dict[str, str]]) -> str:
        raw = json.dumps([model_id, temperature, list(messages)], ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT text FROM completions WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, text: str) -> None:
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO completions (key, text) VALUES (?, ?)", (key, text))
            self._conn.commit()


def _openai_retryable() -> tuple[type[BaseException], ...]:
    import openai

    return (
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
    )


class OpenAIChatLLM:
    def __init__(
        self,
        model_id: str = "gpt-5.6-lunar",
        *,
        temperature: float | None = 0.0,
        base_url: str | None = None,
        api_key: str | None = None,
        cache: LLMCache | None = None,
        max_retries: int = 4,
        client: Any = None,
        retry_on: tuple[type[BaseException], ...] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model_id = model_id
        self.temperature = temperature
        self.cache = cache
        self.max_retries = max_retries
        self._base_url, self._api_key = base_url, api_key
        self._client = client
        self._retry_on = retry_on
        self._sleep = sleep

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            kwargs = {k: v for k, v in (("base_url", self._base_url), ("api_key", self._api_key)) if v}
            self._client = OpenAI(**kwargs)
        return self._client

    def complete(self, system: str, user: str) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        key = LLMCache.key(self.model_id, self.temperature, messages)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return hit

        params: dict[str, Any] = {"model": self.model_id, "messages": messages}
        if self.temperature is not None:
            params["temperature"] = self.temperature
        retry_on = self._retry_on if self._retry_on is not None else _openai_retryable()
        client = self._get_client()
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.chat.completions.create(**params)
                break
            except retry_on as e:
                if attempt == self.max_retries:
                    raise
                wait = min(2**attempt, 30)
                log.warning("LLM lỗi (%r), thử lại sau %ss", e, wait)
                self._sleep(wait)
        text = (resp.choices[0].message.content or "").strip()
        if self.cache is not None:
            self.cache.put(key, text)
        return text


__all__ = ["LLM", "LLMCache", "OpenAIChatLLM"]
