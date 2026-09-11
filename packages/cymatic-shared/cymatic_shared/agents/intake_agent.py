"""Intake Agent - Parses prompt and detects domain/missing fields using LLM"""
from typing import Dict, Any, List
from pydantic import BaseModel, Field
import httpx
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
    # Which analyser produced this result: "llm" (idea-grounded) or "fallback"
    # (keyword templates, not grounded in the idea). Surfaced to the UI so it
    # can show "basic questions (offline mode)" instead of pretending.
    analyser_mode: str = Field(default="llm", description="Analyser path: llm or fallback")


INTAKE_SYSTEM_PROMPT = """You are the Analyser for an AI simulation builder. A user describes an idea or imagination for a walkthrough simulation. Dissect the idea before asking anything.

Step 1 — Idea anatomy. Read the prompt carefully and pull out:
- spaces/rooms or points of interest actually named (quote them)
- style/mood words (modern, ancient, cozy, grand, stone, wooden, ...)
- scale cues (2BHK, single temple, whole complex, floors, sqft, ...)
- materials, lighting, landscape, must-have features
- heritage cues: site type, period/culture, narration needs

Step 2 — Typed entities. Put every concrete fragment you found into extracted_entities using canonical field names with the QUOTED fragment as value (never bare true/false). Example: {"style": "modern", "key_pois": "mandapa, sanctum", "bedrooms": "3-bedroom"}.

Step 3 — Missing fields. List only canonical fields with NO evidence in the prompt.

Step 4 — Grounded questions. Write up to 6 follow-up questions, each tied to a SPECIFIC fragment or gap in THIS idea (reference what the user said, e.g. "You mentioned a 14th-century mandapa — ..."). Generic questions that could apply to any prompt are a failure.

Return JSON with:
- detected_domain: "real_estate" or "heritage"
- objective: original prompt
- missing_fields: array of canonical field names
- suggested_questions: array of up to 6 prioritized, idea-grounded questions
- extracted_entities: object with quoted fragments per canonical field
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

        # Empty/unparseable LLM output must fall back — never treat {} as success.
        # call_llm_json returns {} only when JSON is unrecoverable.
        if not result or not isinstance(result, dict):
            logger.warning("intake_llm_empty_result_fallback")
            return await process_intake_fallback(prompt, context)

        detected = str(result.get("detected_domain", "real_estate")).lower()
        if detected not in ("real_estate", "heritage"):
            logger.warning("intake_llm_invalid_domain", detected=detected)
            detected = "real_estate"

        intake_result = IntakeResult(
            detected_domain=detected,
            objective=result.get("objective", prompt),
            missing_fields=result.get("missing_fields", []),
            suggested_questions=result.get("suggested_questions", [])[:6],
            extracted_entities=result.get("extracted_entities", {}),
            confidence=result.get("confidence", 0.7),
            analyser_mode="llm",
        )

        # LLM returned valid JSON but no usable content -> keyword fallback is better.
        if (
            not intake_result.missing_fields
            and not intake_result.suggested_questions
            and not intake_result.extracted_entities
        ):
            logger.warning("intake_llm_empty_content_fallback")
            return await process_intake_fallback(prompt, context)

        logger.info("intake_llm_completed", domain=intake_result.detected_domain, confidence=intake_result.confidence)
        return intake_result

    except (ValueError, KeyError, OSError, httpx.HTTPError) as e:
        # httpx.HTTPError covers ConnectError/Timeout (router down) and
        # HTTPStatusError (e.g. router 502 when cloud keys are missing).
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
    # Keys aligned with clarification_agent required fields so intake
    # extracted_entities merge cleanly into clarification current_answers.
    # Covers BOTH domains now (heritage previously had no patterns, so heritage
    # ideas matched nothing and always fell back to generic templates).
    "style": ["modern", "traditional", "contemporary", "minimalist", "luxury", "rustic", "victorian", "colonial", "mediterranean"],
    "bedrooms": ["bedroom", "bhk", "master bedroom"],
    "bathrooms": ["bathroom", "bath", "toilet", "ensuite"],
    "square_footage": ["square", "sqft", "sq ft", "feet", "meter", "acre"],
    "budget": ["budget", "price", "cost", "affordable", "expensive", "cheap", "million", "thousand"],
    "floors": ["floor", "story", "storey", "level", "basement", "attic"],
    "furnished": ["furnished", "unfurnished", "semi-furnished"],
    "outdoor_spaces": ["garden", "yard", "pool", "terrace", "balcony", "patio", "deck"],
    "special_rooms": ["office", "study", "gym", "theater", "theatre", "library", "garage"],
    "lighting_preference": ["lighting", "bright", "cozy", "ambient", "sunset", "natural light"],
    "site_type": ["temple", "palace", "courtyard", "monument", "museum", "fort", "mosque", "church", "heritage", "historic"],
    "historical_period": ["century", "ancient", "medieval", "colonial", "mughal", "chola", "vijayanagara", "dynasty", "era"],
    "key_pois": ["mandapa", "sanctum", "garbhagriha", "gopuram", "shikhara", "courtyard", "hall", "shrine", "entrance", "tower"],
    "narration": ["narration", "narrated", "guide", "guided", "audio guide", "commentary"],
    "languages": ["english", "telugu", "hindi", "tamil", "spanish", "french", "language"],
    "scale": ["complex", "single structure", "site", "acres", "compound", "campus"],
    "focus": ["educational", "architectural", "cultural", "spiritual", "tourism", "exploration"],
    "indoor_outdoor": ["indoor", "outdoor", "mixed", "open-air", "covered"],
}

# Canonical required fields per domain (missing_fields is computed against the
# DETECTED domain's set, not the whole pattern superset).
DOMAIN_FIELDS = {
    "real_estate": ["style", "bedrooms", "bathrooms", "square_footage", "floors", "budget", "furnished", "outdoor_spaces", "special_rooms", "lighting_preference"],
    "heritage": ["site_type", "historical_period", "key_pois", "narration", "languages", "scale", "focus", "indoor_outdoor"],
}

# Explicit field -> intake question index for reliable prioritization
# (substring matching fails: "size" not in "square footage?").
FIELD_QUESTION_INDEX = {
    "style": 0,
    "bedrooms": 1,
    "bathrooms": 1,
    "square_footage": 2,
    "budget": 3,
    "floors": 4,
    "outdoor_spaces": 5,
    "furnished": 7,
    "special_rooms": 6,
    "lighting_preference": 5,
    "site_type": 0,
    "historical_period": 1,
    "key_pois": 2,
    "narration": 3,
    "languages": 3,
    "scale": 4,
    "focus": 7,
    "indoor_outdoor": 6,
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
                # Store the matched keyword text (not bare True) so downstream
                # clarification sees a meaningful value instead of a boolean.
                extracted[field] = pattern
                break

    # Determine missing fields against the DETECTED domain's canonical set
    # (previously the whole pattern superset, so real-estate runs demanded
    # heritage fields and vice versa).
    domain_fields = DOMAIN_FIELDS.get(detected_domain, DOMAIN_FIELDS["real_estate"])
    missing_fields = [f for f in domain_fields if f not in mentioned_fields]

    # Get suggested questions
    questions = DOMAIN_QUESTIONS.get(detected_domain, DOMAIN_QUESTIONS["real_estate"])

    # Prioritize questions for missing fields via explicit index map
    # (substring matching is unreliable across vocabularies).
    prioritized_questions = []
    for field in missing_fields:
        idx = FIELD_QUESTION_INDEX.get(field)
        if idx is not None and 0 <= idx < len(questions):
            q = questions[idx]
            if q not in prioritized_questions:
                prioritized_questions.append(q)
            continue
        for q in questions:
            if field.lower() in q.lower() and q not in prioritized_questions:
                prioritized_questions.append(q)
                break

    # Add remaining questions
    for q in questions:
        if q not in prioritized_questions:
            prioritized_questions.append(q)

    # Idea-aware fallback: prefix the top question with what the user actually
    # said so even offline-mode questions reference the idea instead of reading
    # as fully generic. Only when we extracted at least one fragment.
    grounded = list(prioritized_questions[:6])
    if extracted and grounded:
        first_hit = next(iter(extracted.values()), "")
        if isinstance(first_hit, str) and first_hit and grounded[0].lower().find(first_hit.lower()) == -1:
            grounded[0] = f"You mentioned '{first_hit}' — {grounded[0][0].lower() + grounded[0][1:]}"

    return IntakeResult(
        detected_domain=detected_domain,
        objective=prompt,
        missing_fields=missing_fields,
        suggested_questions=grounded,
        extracted_entities=extracted,
        confidence=confidence,
        analyser_mode="fallback",
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
