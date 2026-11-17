"""LLM riêng cho bước gán khái niệm (tagger). Mặc định Claude Haiku 5.5 qua OpenRouter: so 7 model trên hợp đồng
demo 14/11, Haiku 5.5 trích slot đúng 5/5, cùng giá với gpt-6-luna (docs/superpowers/notes/2026-11-14-tag-model-compare.md).

CONCEPT_TAG_MODEL = id model OpenRouter, hoặc "app" để dùng LLM của app. Thiếu OPENROUTER_API_KEY -> dùng LLM của app.
Không gửi temperature: Claude 5.x / GPT-6 từ chối giá trị khác mặc định."""
from __future__ import annotations

import logging

from rag.config import Settings
from rag.generate.llm import LLMCache, OpenAIChatLLM

log = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1"


def concept_tag_llm(settings: Settings, cache: LLMCache | None = None) -> OpenAIChatLLM | None:
    """LLM cho tagger; None -> người gọi dùng LLM của app."""
    return _openrouter_llm(settings.concept_tag_model, settings, cache)


def contract_agent_llm(settings: Settings, cache: LLMCache | None = None) -> OpenAIChatLLM | None:
    """LLM cho agent trên đồ thị hợp đồng (CONTRACT_AGENT_MODEL, mặc định "app"); None -> dùng LLM của app."""
    return _openrouter_llm(settings.contract_agent_model, settings, cache)


def _openrouter_llm(model: str | None, settings: Settings, cache: LLMCache | None) -> OpenAIChatLLM | None:
    model = (model or "").strip()
    if not model or model == "app":
        return None
    if not settings.openrouter_api_key:
        log.warning("Không có OPENROUTER_API_KEY: gán khái niệm dùng LLM của app thay cho %s", model)
        return None
    return OpenAIChatLLM(model, temperature=None, base_url=OPENROUTER_URL, api_key=settings.openrouter_api_key,
                         cache=cache)


__all__ = ["OPENROUTER_URL", "concept_tag_llm", "contract_agent_llm"]
