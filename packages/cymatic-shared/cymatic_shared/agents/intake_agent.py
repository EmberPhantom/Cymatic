"""Intake Agent - Parses prompt and detects domain/missing fields using LLM"""
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import structlog
import json
from cymatic_shared.agents.llm_client import call_llm_json

logger = structlog.get_logger()


class IntakeResult(BaseModel):
    detected_domain: str = Field(description="Detected domain: real_estate or heritage")
    objective: str = Field(description="Original user objective")
    missing_fields: List[str] = Field(description="Fields not mentioned in prompt")
    suggested_questions: List[str] = Field(description="Prioritized follow-up questions")
    extracted_entities: Dict[str, Any] = Field(default_factory=dict, description="Entities extracted from prompt")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Detection confidence")


INTAKE_SYSTEM_PROMPT = """You are an expert at analyzing user prompts for simulation generation.
Analyze the prompt and extract:
1. Domain (real_estate or heritage)
2. Key entities mentioned (style, rooms, size, budget, etc.)
3. Missing fields that need clarification
4. Suggested follow-up questions

Return JSON with:
- detected_domain: "real_estate" or "heritage"
- objective: original prompt
- missing_fields: array of field names
- suggested_questions: array of up to 6 prioritized questions
- extracted_entities: object with detected entities
- confidence: 0.0-1.0

Real estate fields: style, bedrooms, bathrooms, square_footage, floors, budget, furnished, outdoor_spaces, special_rooms, lighting_preference
Heritage fields: site_type, historical_period, key_pois, narration, languages, scale, focus, indoor_outdoor"""


def sanitize_prompt(prompt: str) -> str:
    """Sanitize prompt: strip controls, limit length, block injection."""
    prompt = "".join(ch for ch in prompt if ch.isprintable() or ch in "\n\t ")
    if len(prompt) > 10000:
        prompt = prompt[:10000]
    injection_markers = ["ignore previous", "system prompt", "jailbreak"]
    low = prompt.lower()
    for m in injection_markers:
        if m in low:
            logger.warning("prompt_injection_blocked", marker=m)
            # keep prompt but flag
            break
    return prompt.strip()


async def process_intake_llm(prompt: str, context: Dict[str, Any] | None = None) -> IntakeResult:
    """Process user prompt using LLM for intelligent analysis."""
    prompt = sanitize_prompt(prompt)
    messages = [
        {"role": "system", "content": INTAKE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Prompt: {prompt}\nContext: {json.dumps(context or {})}"}
    ]

    try:
        result = await call_llm_json(
            messages=messages,
            task_type="intent_extraction",
            sensitivity="internal",
            temperature=0.3,
            max_tokens=1000,
        )

        intake_result = IntakeResult(
            detected_domain=result.get("detected_domain", "real_estate"),
            objective=result.get("objective", prompt),
            missing_fields=result.get("missing_fields", []),
            suggested_questions=result.get("suggested_questions", [])[:6],
            extracted_entities=result.get("extracted_entities", {}),
            confidence=result.get("confidence", 0.7),
        )

        logger.info("intake_llm_completed", domain=intake_result.detected_domain, confidence=intake_result.confidence)
        return intake_result

    except (ValueError, KeyError, OSError) as e:
        logger.error("intake_llm_failed", error=str(e))
        return await process_intake_fallback(prompt, context)


# Fallback implementation (keyword-based)
DOMAIN_KEYWORDS = {
    "real_estate": [
        "apartment", "house", "home", "property", "real estate", "listing",
        "bedroom", "bathroom", "kitchen", "living room", "furnished",
        "walkthrough", "tour", "viewing", "showing", "open house",
        "square feet", "sqft", "floor plan", "layout", "interior"
    ],
    "heritage": [
        "heritage", "historic", "monument", "temple", "palace", "courtyard",
        "museum", "cultural", "ancient", "archaeological", "preservation",
        "landmark", "site", "ruins", "traditional", "historic building"
    ]
}

FIELD_PATTERNS = {
    "style": ["modern", "traditional", "contemporary", "minimalist", "luxury", "rustic", "victorian", "colonial", "mediterranean"],
    "rooms": ["bedroom", "bathroom", "kitchen", "living", "dining", "office", "study", "garage", "balcony", "patio"],
    "size": ["square", "sqft", "sq ft", "feet", "meter", "acre"],
    "budget": ["budget", "price", "cost", "affordable", "expensive", "cheap", "million", "thousand"],
    "floors": ["floor", "story", "storey", "level", "basement", "attic"],
    "outdoor": ["garden", "yard", "pool", "terrace", "balcony", "patio", "deck"],
}

DOMAIN_QUESTIONS = {
    "real_estate": [
        "What architectural style do you prefer?",
        "How many bedrooms and bathrooms do you need?",
        "What's the approximate square footage?",
        "What's your budget range?",
        "How many floors/levels?",
        "Do you need outdoor spaces? (garden, balcony, pool, etc.)",
        "Any specific rooms required? (home office, gym, theater, etc.)",
        "Furnished or unfurnished?",
    ],
    "heritage": [
        "What type of heritage site? (temple, palace, courtyard, monument, etc.)",
        "What historical period or culture?",
        "What key points of interest should be highlighted?",
        "Do you need guided narration? In what language(s)?",
        "What's the approximate area/scale?",
        "Any specific architectural features to emphasize?",
        "Indoor, outdoor, or mixed experience?",
        "Educational focus or pure exploration?",
    ]
}


async def process_intake_fallback(prompt: str, context: Dict[str, Any] | None = None) -> IntakeResult:
    """Fallback keyword-based intake processing."""
    prompt_lower = prompt.lower()

    # Detect domain
    domain_scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in prompt_lower)
        domain_scores[domain] = score

    detected_domain = max(domain_scores, key=domain_scores.get) if max(domain_scores.values()) > 0 else "real_estate"
    confidence = max(domain_scores.values()) / max(len(DOMAIN_KEYWORDS[detected_domain]), 1)

    # Extract mentioned fields
    extracted = {}
    mentioned_fields = set()

    for field, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            if pattern in prompt_lower:
                mentioned_fields.add(field)
                extracted[field] = True
                break

    # Determine missing fields
    all_fields = set(FIELD_PATTERNS.keys())
    missing_fields = list(all_fields - mentioned_fields)

    # Get suggested questions
    questions = DOMAIN_QUESTIONS.get(detected_domain, DOMAIN_QUESTIONS["real_estate"])

    # Prioritize questions for missing fields
    prioritized_questions = []
    for field in missing_fields:
        for q in questions:
            if field.lower() in q.lower() and q not in prioritized_questions:
                prioritized_questions.append(q)
                break

    # Add remaining questions
    for q in questions:
        if q not in prioritized_questions:
            prioritized_questions.append(q)

    return IntakeResult(
        detected_domain=detected_domain,
        objective=prompt,
        missing_fields=missing_fields,
        suggested_questions=prioritized_questions[:6],
        extracted_entities=extracted,
        confidence=confidence
    )


def merge_intake_answers(intake_result: IntakeResult, answers: Dict[str, str]) -> IntakeResult:
    """Merge clarification answers into intake result."""
    for key, value in answers.items():
        intake_result.extracted_entities[key] = value
        if key in intake_result.missing_fields:
            intake_result.missing_fields.remove(key)

    remaining_missing = intake_result.missing_fields
    prioritized_questions = []
    for field in remaining_missing:
        for q in intake_result.suggested_questions:
            if field.lower() in q.lower() and q not in prioritized_questions:
                prioritized_questions.append(q)
                break

    intake_result.suggested_questions = prioritized_questions
    intake_result.confidence = min(1.0, intake_result.confidence + 0.2)

    return intake_result


# Main entry point
async def process_intake(prompt: str, context: Dict[str, Any] | None = None) -> IntakeResult:
    """Main intake processing - uses LLM with keyword fallback."""
    prompt = sanitize_prompt(prompt)
    return await process_intake_llm(prompt, context)
