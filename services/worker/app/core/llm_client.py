"""LLM Router Client - re-export from shared package"""
from cymatic_shared.agents.llm_client import (
    LLMRouterClient,
    llm_router_client,
    call_llm,
    call_llm_json,
    call_llm_structured,
)

__all__ = [
    "LLMRouterClient",
    "llm_router_client",
    "call_llm",
    "call_llm_json",
    "call_llm_structured",
]
