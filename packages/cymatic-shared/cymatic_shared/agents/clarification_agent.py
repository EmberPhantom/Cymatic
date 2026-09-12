"""Clarification Agent - Asks targeted follow-up questions using LLM"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import httpx
import re
import structlog
import json
from cymatic_shared.agents.intake_agent import FIELD_PATTERNS
from cymatic_shared.agents.llm_client import call_llm_json

logger = structlog.get_logger()


class ClarificationQuestion(BaseModel):
    field: str
    question: str
    type: str  # "text", "choice", "number", "boolean"
    options: List[str] = Field(default_factory=list)
    required: bool = True
    depends_on: Optional[str] = None
    # Quoted fragment of the user's idea this question addresses (or the gap
    # it fills). Forces input-grounding; surfaced in logs/traces for audit.
    evidence_span: Optional[str] = None
    # Adaptive-UI metadata: units, numeric bounds, multi-select.
    unit: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    multi: bool = False


class ClarificationResult(BaseModel):
    questions: List[ClarificationQuestion]
    updated_fields: Dict[str, Any]
    ready_for_generation: bool
    completion_percentage: float
    # Which analyser produced this result: "llm" (idea-grounded) or "fallback"
    # (templates, only echoing extracted fragments). Surfaced to the UI.
    analyser_mode: str = "llm"
    # Raw free-text answers that failed field validation (kept for context,
    # never used as entities).
    answer_notes: Dict[str, str] = Field(default_factory=dict)


CLARIFICATION_SYSTEM_PROMPT = """You are the Analyser for an AI simulation builder. The user described an idea for a walkthrough simulation. Ask follow-up questions that prove you read THEIR idea.

You receive: domain, current answered fields, new user answers, plus original_prompt / objective / intake_entities (quoted fragments from the idea).

Rules:
1. Convert answers to appropriate types.
2. Every remaining question MUST address a specific fragment or gap in THIS idea: set evidence_span to the quoted fragment it builds on (e.g. "14th-century mandapa") or the explicit gap (e.g. "no style mentioned").
3. Reference the idea inside the question text where natural ("You mentioned a mandapa and sanctum — ..."). Generic questions that fit any prompt are a failure.
4. Determine which required fields remain, calculate completion percentage, check readiness (all required fields answered).

Return JSON with:
- questions: array of remaining ClarificationQuestion objects
- updated_fields: object with all fields (converted to proper types)
- ready_for_generation: boolean
- completion_percentage: 0.0-1.0

Question format:
- field: string (canonical field name)
- question: string (idea-grounded, references what the user said)
- type: "text" | "choice" | "number" | "boolean"
- options: array of strings (for choice type)
- required: boolean
- depends_on: string or null
- evidence_span: string (quoted idea fragment or gap description)
- unit: string or null (e.g. "sqft", "count" — for number type)
- min_value / max_value: numbers or null (for number type)
- multi: boolean (true when several options may be selected)

Real estate required fields: style, bedrooms, bathrooms, square_footage, furnished
Heritage required fields: site_type, historical_period, key_pois, narration, scale, focus, indoor_outdoor"""


# Question templates (fallback)
DOMAIN_QUESTIONS = {
    "real_estate": [
        ClarificationQuestion(field="style", question="What architectural style do you prefer?", type="choice", options=["Modern", "Traditional", "Contemporary", "Minimalist", "Luxury", "Rustic", "Mediterranean", "Colonial", "Victorian", "Other"], required=True),
        ClarificationQuestion(field="bedrooms", question="How many bedrooms do you need?", type="number", required=True, unit="count", min_value=1, max_value=20),
        ClarificationQuestion(field="bathrooms", question="How many bathrooms?", type="number", required=True, unit="count", min_value=1, max_value=20),
        ClarificationQuestion(field="square_footage", question="What's the approximate square footage?", type="number", required=True, unit="sqft", min_value=100, max_value=100000),
        ClarificationQuestion(field="floors", question="How many floors/levels?", type="number", required=False, unit="count", min_value=1, max_value=10),
        ClarificationQuestion(field="budget", question="What's your budget range?", type="choice", options=["Under $500K", "$500K-$1M", "$1M-$2M", "$2M-$5M", "$5M+", "Not specified"], required=False),
        ClarificationQuestion(field="furnished", question="Should the walkthrough show furnished or unfurnished spaces?", type="choice", options=["Furnished", "Unfurnished", "Partially furnished"], required=True),
        ClarificationQuestion(field="outdoor_spaces", question="Which outdoor spaces should be included?", type="choice", options=["Garden", "Balcony", "Terrace", "Pool", "Patio", "Deck", "None"], required=False, multi=True),
        ClarificationQuestion(field="special_rooms", question="Any special rooms needed?", type="text", required=False),
        ClarificationQuestion(field="lighting_preference", question="What lighting mood do you prefer?", type="choice", options=["Warm/Cozy", "Bright/Natural", "Cool/Modern", "Golden Hour", "Evening/Ambient"], required=False),
    ],
    "heritage": [
        ClarificationQuestion(field="site_type", question="What type of heritage site?", type="choice", options=["Temple", "Palace", "Courtyard", "Monument", "Mausoleum", "Historic Building", "Archaeological Site", "Museum", "Cultural Landscape"], required=True),
        ClarificationQuestion(field="historical_period", question="What historical period or culture?", type="text", required=True),
        ClarificationQuestion(field="key_pois", question="What are the key points of interest to highlight?", type="text", required=True),
        ClarificationQuestion(field="narration", question="Do you need guided narration?", type="boolean", required=True),
        ClarificationQuestion(field="languages", question="What languages for narration?", type="choice", options=["English", "Telugu", "Hindi", "Spanish", "French", "German", "Japanese", "Chinese", "Arabic"], required=False, depends_on="narration", multi=True),
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


# Maps legacy intake free-text questions (and common answer keys) to canonical
# clarification field names. The frontend previously used the full question
# sentence as `field`, so answers arrived as {"What architectural style...": v}
# and never matched required fields. Normalizing fixes the 0% completion loop
# while staying backward compatible.
QUESTION_TEXT_TO_FIELD: Dict[str, str] = {
    "what architectural style do you prefer?": "style",
    "how many bedrooms and bathrooms do you need?": "bedrooms",
    "how many bedrooms do you need?": "bedrooms",
    "how many bathrooms?": "bathrooms",
    "what's the approximate square footage?": "square_footage",
    "what is the approximate square footage?": "square_footage",
    "what's your budget range?": "budget",
    "what is your budget range?": "budget",
    "how many floors/levels?": "floors",
    "how many floors?": "floors",
    "do you need outdoor spaces? (garden, balcony, pool, etc.)": "outdoor_spaces",
    "which outdoor spaces should be included?": "outdoor_spaces",
    "any specific rooms required? (home office, gym, theater, etc.)": "special_rooms",
    "any special rooms needed?": "special_rooms",
    "furnished or unfurnished?": "furnished",
    "should the walkthrough show furnished or unfurnished spaces?": "furnished",
    "what lighting mood do you prefer?": "lighting_preference",
    "what type of heritage site? (temple, palace, courtyard, monument, etc.)": "site_type",
    "what type of heritage site?": "site_type",
    "what historical period or culture?": "historical_period",
    "what key points of interest should be highlighted?": "key_pois",
    "what are the key points of interest to highlight?": "key_pois",
    "do you need guided narration? in what language(s)?": "narration",
    "do you need guided narration?": "narration",
    "what languages for narration?": "languages",
    "what's the approximate area/scale?": "scale",
    "what's the approximate scale/area?": "scale",
    "any specific architectural features to emphasize?": "focus",
    "what's the primary focus?": "focus",
    "indoor, outdoor, or mixed experience?": "indoor_outdoor",
    "is the experience indoor, outdoor, or mixed?": "indoor_outdoor",
    "educational focus or pure exploration?": "focus",
    # Common short-key aliases from keyword fallback
    "rooms": "bedrooms",
    "size": "square_footage",
    "outdoor": "outdoor_spaces",
}


def normalize_answer_keys(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Map legacy sentence-keys / aliases to canonical clarification fields."""
    normalized: Dict[str, Any] = {}
    for key, value in (answers or {}).items():
        if not isinstance(key, str):
            continue
        stripped = key.strip()
        canonical = QUESTION_TEXT_TO_FIELD.get(stripped.lower(), stripped)
        # Also handle "field: question" composites defensively
        if canonical == stripped and ":" in stripped:
            head = stripped.split(":", 1)[0].strip().lower()
            canonical = QUESTION_TEXT_TO_FIELD.get(head, stripped)
        # Canonical fields are snake_case without spaces; only remap when the
        # lookup hit — otherwise preserve the original key verbatim.
        normalized[canonical] = value
    return normalized


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
    new_answers: Dict[str, str],
    prompt: Optional[str] = None,
    objective: Optional[str] = None,
    intake_entities: Optional[Dict[str, Any]] = None,
) -> ClarificationResult:
    """Process clarification using LLM."""
    # Normalize legacy sentence-keys so old frontend payloads still resolve.
    current_answers = normalize_answer_keys(current_answers or {})
    new_answers = normalize_answer_keys(new_answers or {})
    # Merge answers first (fresh answers win over stale intake).
    updated = {**current_answers, **(intake_entities or {})}
    for key, value in new_answers.items():
        updated[key] = convert_value(value, domain, key) if isinstance(value, str) else value

    user_payload: Dict[str, Any] = {
        "domain": domain,
        "current_answers": updated,
        "new_answers": new_answers,
    }
    # Prompt/objective context lets the LLM ask prompt-specific questions
    # (e.g. "you said 14th-century mandapa...") instead of generic templates.
    if prompt:
        user_payload["original_prompt"] = prompt[:2000]
    if objective:
        user_payload["objective"] = objective[:2000]
    if intake_entities:
        user_payload["intake_entities"] = intake_entities

    messages = [
        {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload)}
    ]

    try:
        result = await call_llm_json(
            messages=messages,
            task_type="clarification",
            sensitivity="internal",
            temperature=0.3,
            max_tokens=2000,
        )

        # Empty/unparseable output must use the deterministic fallback.
        if not result or not isinstance(result, dict):
            logger.warning("clarification_llm_empty_result_fallback", domain=domain)
            return process_clarification_fallback(domain, current_answers, new_answers)

        questions = [ClarificationQuestion(**q) for q in result.get("questions", [])]

        ready = bool(result.get("ready_for_generation", False))
        # LLM returned no questions but claims not ready -> fallback knows the
        # full required-field list and is more useful than an empty loop.
        if not questions and not ready:
            logger.warning("clarification_llm_no_questions_fallback", domain=domain)
            return process_clarification_fallback(domain, current_answers, new_answers)

        return ClarificationResult(
            questions=questions,
            updated_fields=result.get("updated_fields", updated),
            ready_for_generation=ready,
            completion_percentage=float(result.get("completion_percentage", 0.0)),
            analyser_mode="llm",
        )

    except (ValueError, KeyError, OSError, httpx.HTTPError) as e:
        logger.error("clarification_llm_failed", error=str(e))
        return process_clarification_fallback(domain, current_answers, new_answers)


def _clean_fallback_answer(field: str, value: Any, domain: str) -> tuple[Any | None, str | None]:
    """Validate a free-text fallback answer against the field's question type.

    Returns (clean_value, raw_note). Free sentences ("when it was built...")
    are NOT clean values — storing them as entities poisons the architect and
    domain checks (live Taj run: site_type became "palace."). Raw text is
    always kept as a note so intent isn't lost.
    """
    raw = value if isinstance(value, str) else None
    if not isinstance(value, str):
        return value, None
    text = value.strip().strip(".").strip()
    if not text:
        return None, raw
    questions = {q.field: q for q in DOMAIN_QUESTIONS.get(domain, [])}
    q = questions.get(field)
    if q is None:
        return (text[:80] if len(text) <= 80 else None), raw
    low = text.lower()
    if q.type == "choice" and q.options:
        opt_lows = [o.lower() for o in q.options]
        # Multi-select first ("english,telugu"): a single-option prefix match
        # must not swallow the rest of the list.
        if "," in text or "/" in text:
            parts = [p.strip() for p in re.split(r"[,/]", text) if p.strip()]
            if parts and all(
                p.lower() in opt_lows or any(p.lower() in o.split("/") for o in opt_lows) for p in parts
            ):
                return text, raw
        for opt in q.options:
            if opt.lower() == low or low in opt.lower().split("/") or opt.lower() in low:
                return opt, raw
        if len(text) <= 40 and len(parts) <= 3:
            return text, raw
        return None, raw
    if q.type == "number":
        try:
            return (int(text) if "." not in text else float(text)), raw
        except ValueError:
            m = re.search(r"\d+(\.\d+)?", text)
            return (float(m.group(0)) if m else None), raw
    if q.type == "boolean":
        if re.search(r"\byes\b|\btrue\b|\by\b", low):
            return True, raw
        if re.search(r"\bno\b|\bfalse\b|\bnone\b|\bnot\b", low):
            return False, raw
        return None, raw
    # text: accept concise fragments or vocabulary-grounded phrases; reject
    # free sentences ("when it was built for the first time").
    words = text.split()
    if len(text) <= 80 and (
        len(words) <= 5
        or re.search(r"\d", text)
        or any(pat in low for pat in FIELD_PATTERNS.get(field, []))
    ):
        return text, raw
    return None, raw


def process_clarification_fallback(
    domain: str,
    current_answers: Dict[str, Any],
    new_answers: Dict[str, str],
) -> ClarificationResult:
    """Fallback processing without LLM."""
    current_answers = normalize_answer_keys(current_answers or {})
    new_answers_norm = normalize_answer_keys(new_answers or {})
    updated = current_answers.copy()
    notes: Dict[str, str] = {}
    for key, value in new_answers_norm.items():
        clean, raw = _clean_fallback_answer(key, value, domain) if isinstance(value, str) else (value, None)
        if raw is not None:
            notes[key] = raw
        if clean is None:
            # Invalid free text: never overwrite a good existing entity.
            continue
        updated[key] = clean

    remaining_questions = get_fallback_questions(domain, updated)

    # Idea-aware fallback: attach evidence spans from extracted fragments so
    # even offline-mode questions echo the user's idea, and ground the most
    # relevant question in a quoted fragment.
    for q in remaining_questions:
        if q.evidence_span:
            continue
        fragment = updated.get(q.field)
        if isinstance(fragment, str) and fragment and fragment.lower() not in ("true", "false"):
            q.evidence_span = fragment[:200]
        else:
            # No evidence for this field in the idea: mark the gap explicitly.
            q.evidence_span = f"no {q.field} mentioned in idea"
    if remaining_questions:
        # Ground the top question in the strongest available fragment.
        top = remaining_questions[0]
        best = ""
        for v in updated.values():
            if isinstance(v, str) and len(v) > len(best) and v.lower() not in ("true", "false"):
                best = v[:200]
        if best and (not top.evidence_span or top.evidence_span.startswith("no ")):
            top.evidence_span = best

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
        analyser_mode="fallback",
        answer_notes=notes,
    )


# Main entry point
async def process_clarification_answers(
    domain: str,
    current_answers: Dict[str, Any],
    new_answers: Dict[str, str],
    prompt: Optional[str] = None,
    objective: Optional[str] = None,
    intake_entities: Optional[Dict[str, Any]] = None,
) -> ClarificationResult:
    """Main clarification processing - uses LLM with fallback."""
    return await process_clarification_llm(
        domain, current_answers, new_answers, prompt, objective, intake_entities
    )


def get_clarification_questions(domain: str, answered_fields: Dict[str, Any]) -> List[ClarificationQuestion]:
    """Get questions for domain (fallback only - LLM version generates dynamically)."""
    return get_fallback_questions(domain, answered_fields)
