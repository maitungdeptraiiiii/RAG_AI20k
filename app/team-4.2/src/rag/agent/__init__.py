"""Opt-in, evidence-grounded multi-hop agent; baseline RAG remains separate."""

from rag.agent.contracts import AgentConfig
from rag.agent.orchestrator import AgentPipeline

__all__ = ["AgentConfig", "AgentPipeline"]
