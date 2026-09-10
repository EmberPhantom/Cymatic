"""Clarification Agent - Asks targeted follow-up questions using LLM"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import httpx
import structlog
import json
from cymatic_shared.agents.llm_client import call_llm_json

logger = structlog.get_logger()


class ClarificationQuestion(BaseModel):
    field: str
    question: str
    type: str  # "text", "choice", "number", "boolean"
    options: List[str] = Field(default_factory=list)
    required: bool = True
    depends_on: Optional[str] = None


class ClarificationResult(BaseModel):
    questions: List[ClarificationQuestion]
    updated_fields: Dict[str, Any]
    ready_for_generation: bool
    completion_percentage: float


CLARIFICATION_SYSTEM_PROMPT = """You are an expert at generating targeted follow-up questions for simulation specification.

Given a domain, current answered fields, and new user answers:
1. Convert answers to appropriate types
2. Determine which questions remain
3. Calculate completion percentage
4. Check if ready for generation (all required fields answered)

Return JSON with:
- questions: array of remaining ClarificationQuestion objects
- updated_fields: object with all fields (converted to proper types)
- ready_for_generation: boolean
- completion_percentage: 0.0-1.0

Question format:
- field: string
- question: string
- type: "text" | "choice" | "number" | "boolean"
- options: array of strings (for choice type)
- required: boolean
- depends_on: string or null

Real estate required fields: style, bedrooms, bathrooms, square_footage, furnished
Heritage required fields: site_type, historical_period, key_pois, narration, scale, focus, indoor_outdoor"""


# Question templates (fallback)
DOMAIN_QUESTIONS = {
    "real_estate": [
        ClarificationQuestion(field="style", question="What architectural style do you prefer?", type="choice", options=["Modern", "Traditional", "Contemporary", "Minimalist", "Luxury", "Rustic", "Mediterranean", "Colonial", "Victorian", "Other"], required=True),
        ClarificationQuestion(field="bedrooms", question="How many bedrooms do you need?", type="number", required=True),
        ClarificationQuestion(field="bathrooms", question="How many bathrooms?", type="number", required=True),
        ClarificationQuestion(field="square_footage", question="What's the approximate square footage?", type="number", required=True),
        ClarificationQuestion(field="floors", question="How many floors/levels?", type="number", required=False),
        ClarificationQuestion(field="budget", question="What's your budget range?", type="choice", options=["Under $500K", "$500K-$1M", "$1M-$2M", "$2M-$5M", "$5M+", "Not specified"], required=False),
        ClarificationQuestion(field="furnished", question="Should the walkthrough show furnished or unfurnished spaces?", type="choice", options=["Furnished", "Unfurnished", "Partially furnished"], required=True),
        ClarificationQuestion(field="outdoor_spaces", question="Which outdoor spaces should be included?", type="choice", options=["Garden", "Balcony", "Terrace", "Pool", "Patio", "Deck", "None"], required=False),
        ClarificationQuestion(field="special_rooms", question="Any special rooms needed?", type="text", required=False),
        ClarificationQuestion(field="lighting_preference", question="What lighting mood do you prefer?", type="choice", options=["Warm/Cozy", "Bright/Natural", "Cool/Modern", "Golden Hour", "Evening/Ambient"], required=False),
    ],
    "heritage": [
        ClarificationQuestion(field="site_type", question="What type of heritage site?", type="choice", options=["Temple", "Palace", "Courtyard", "Monument", "Historic Building", "Archaeological Site", "Museum", "Cultural Landscape"], required=True),
        ClarificationQuestion(field="historical_period", question="What historical period or culture?", type="text", required=True),
        ClarificationQuestion(field="key_pois", question="What are the key points of interest to highlight?", type="text", required=True),
        ClarificationQuestion(field="narration", question="Do you need guided narration?", type="boolean", required=True),
        ClarificationQuestion(field="languages", question="What languages for narration?", type="choice", options=["English", "Telugu", "Hindi", "Spanish", "French", "German", "Japanese", "Chinese", "Arabic"], required=False, depends_on="narration"),
        ClarificationQuestion(field="scale", question="What's the approximate scale/area?", type="choice", options=["Small (single structure)", "Medium (complex)", "Large (site/multiple buildings)", "Not sure"], required=True),
        ClarificationQuestion(field="focus", question="What's the primary focus?", type="choice", options=["Educational/Historical", "Architectural Detail", "Cultural Experience", "Spiritual/Religious", "Tourism/Exploration"], required=True),
        ClarificationQuestion(field="indoor_outdoor", question="Is the experience indoor, outdoor, or mixed?", type="choice", options=["Indoor", "Outdoor", "Mixed"], required=True),
    ]
}


def get_fallback_questions(domain: str, answered_fields: Dict[str, Any]) -> List[ClarificationQuestion]:
    """Get fallback questions."""
    all_questions = DOMAIN_QUESTIONS.get(domain, DOMAIN_QUESTIONS["real_estate"])
    relevant = []
    for q in all_questions:
        if q.field in answered_fields:
            continue
        if q.depends_on and q.depends_on in answered_fields:
            dep_value = answered_fields[q.depends_on]
            if isinstance(dep_value, bool) and not dep_value:
                continue
            if isinstance(dep_value, str) and dep_value.lower() in ["no", "false", "none"]:
                continue
        relevant.append(q)
    return relevant


def convert_value(value: str, domain: str, field: str) -> Any:
    """Convert string answer to appropriate type."""
    value = value.strip()

    # Boolean fields
    if field in ["narration", "furnished"]:
        return value.lower() in ["yes", "true", "furnished", "guided", "with narration"]

    # Number fields
    if field in ["bedrooms", "bathrooms", "square_footage", "floors"]:
        try:
            return int(value)
        except ValueError:
            return value

    return value


async def process_clarification_llm(
    domain: str,
    current_answers: Dict[str, Any],
    new_answers: Dict[str, str]
) -> ClarificationResult:
    """Process clarification using LLM."""
    # Merge answers first
    updated = current_answers.copy()
    for key, value in new_answers.items():
        updated[key] = convert_value(value, domain, key)

    messages = [
        {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "domain": domain,
            "current_answers": updated,
            "new_answers": new_answers,
        })}
    ]

    try:
        result = await call_llm_json(
            messages=messages,
            task_type="clarification",
            sensitivity="internal",
            temperature=0.3,
            max_tokens=2000,
        )

        questions = [ClarificationQuestion(**q) for q in result.get("questions", [])]

        return ClarificationResult(
            questions=questions,
            updated_fields=result.get("updated_fields", updated),
            ready_for_generation=result.get("ready_for_generation", False),
            completion_percentage=result.get("completion_percentage", 0.0),
        )

    except (ValueError, KeyError, OSError, httpx.HTTPError) as e:
        logger.error("clarification_llm_failed", error=str(e))
        return process_clarification_fallback(domain, current_answers, new_answers)


def process_clarification_fallback(
    domain: str,
    current_answers: Dict[str, Any],
    new_answers: Dict[str, str]
) -> ClarificationResult:
    """Fallback processing without LLM."""
    updated = current_answers.copy()
    for key, value in new_answers.items():
        updated[key] = convert_value(value, domain, key)

    remaining_questions = get_fallback_questions(domain, updated)

    total_questions = len(DOMAIN_QUESTIONS.get(domain, []))
    answered_count = len([f for f in updated if f in [q.field for q in DOMAIN_QUESTIONS.get(domain, [])]])
    completion = answered_count / max(total_questions, 1)

    required_fields = [q.field for q in DOMAIN_QUESTIONS.get(domain, []) if q.required]
    ready = all(f in updated for f in required_fields)

    return ClarificationResult(
        questions=remaining_questions,
        updated_fields=updated,
        ready_for_generation=ready,
        completion_percentage=completion,
    )


# Main entry point
async def process_clarification_answers(
    domain: str,
    current_answers: Dict[str, Any],
    new_answers: Dict[str, str]
) -> ClarificationResult:
    """Main clarification processing - uses LLM with fallback."""
    return await process_clarification_llm(domain, current_answers, new_answers)


def get_clarification_questions(domain: str, answered_fields: Dict[str, Any]) -> List[ClarificationQuestion]:
    """Get questions for domain (fallback only - LLM version generates dynamically)."""
    return get_fallback_questions(domain, answered_fields)
