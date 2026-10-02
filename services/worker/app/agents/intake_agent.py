"""Intake Agent - re-export from shared package"""

from cymatic_shared.agents.intake_agent import (
    process_intake,
    process_intake_llm,
    process_intake_fallback,
    merge_intake_answers,
    IntakeResult,
    DOMAIN_KEYWORDS,
    FIELD_PATTERNS,
    DOMAIN_QUESTIONS,
)

__all__ = [
    "process_intake",
    "process_intake_llm",
    "process_intake_fallback",
    "merge_intake_answers",
    "IntakeResult",
    "DOMAIN_KEYWORDS",
    "FIELD_PATTERNS",
    "DOMAIN_QUESTIONS",
]
