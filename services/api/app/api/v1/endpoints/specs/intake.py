"""Specs sub-router (split from specs.py, no logic change)."""

import copy
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from app.core.config import get_settings
from app.core.dependencies import require_creator
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.models import GenerationRun
from cymatic_shared.ids import new_run_id
from cymatic_shared.model_enums import RunStatus, RunStage
from .schemas import (
    SpecGenerateRequest,
    SpecClarifyRequest,
    ClarifyWithStateRequest,
)

# NOTE: agent entry points resolve via the specs package namespace
# (app.api.v1.endpoints.specs.process_*) so tests can monkeypatch them.
from app.api.v1.endpoints import specs as _specs_ns

settings = get_settings()

router = APIRouter()


@router.post(
    "/{project_id}/intake",
    response_model=Dict[str, Any],
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_LLM))],
)
async def intake_prompt(
    project_id: int,
    request: SpecGenerateRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Parse initial prompt and detect domain/missing fields using Intake Agent"""
    # Verify project access
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Use Intake Agent and persist the result for the subsequent stages.
    # Merge project.domain into context so the LLM sees the creation-time
    # domain alongside the prompt (frontend sends only {prompt} today).
    effective_context = dict(request.context or {})
    effective_context.setdefault("project_domain", project.domain)
    import time as _time

    import structlog as _structlog

    _intake_start = _time.monotonic()
    intake_result = await _specs_ns.process_intake(request.prompt, effective_context)
    _structlog.get_logger().info(
        "intake_completed",
        project_id=project_id,
        analyser_mode=intake_result.analyser_mode,
        duration_ms=round((_time.monotonic() - _intake_start) * 1000, 2),
    )
    # Deep copy context to avoid mutation after enqueue
    context_copy = copy.deepcopy(effective_context)
    input_hash = hashlib.sha256(
        json.dumps(
            {"prompt": request.prompt, "context": context_copy}, sort_keys=True
        ).encode()
    ).hexdigest()
    # Stash plain values now: after a rollback below, ORM attribute access on
    # project/current_user would lazy-load (expired state) and raise
    # MissingGreenlet in async context.
    org_id = project.organization_id
    run = GenerationRun(
        id=new_run_id(),
        project_id=project_id,
        organization_id=org_id,
        prompt=request.prompt,
        context_json=copy.deepcopy(context_copy),
        intake_json=copy.deepcopy(intake_result.model_dump()),
        clarification_json={},
        input_hash=input_hash,
        stage=RunStage.CLARIFICATION if intake_result.missing_fields else RunStage.SPEC,
        status=RunStatus.NEEDS_CLARIFICATION
        if intake_result.missing_fields
        else RunStatus.READY_FOR_SPEC,
        progress=15 if intake_result.missing_fields else 25,
    )
    db.add(run)
    try:
        await db.commit()
    except IntegrityError:
        # Retry-after-timeout resubmits the same prompt+context, tripping the
        # unique (project_id, input_hash) constraint. Return the existing run
        # instead of a 500 (mirrors generate-spec's "already queued" dedupe).
        await db.rollback()
        import structlog as _structlog_dedupe

        _structlog_dedupe.get_logger().info(
            "intake_dedupe_hit", project_id=project_id, input_hash=input_hash
        )
        existing = await db.scalar(
            select(GenerationRun).where(
                GenerationRun.project_id == project_id,
                GenerationRun.organization_id == org_id,
                GenerationRun.input_hash == input_hash,
            )
        )
        if existing is None:
            raise
        stored = existing.intake_json or {}
        return {
            "detected_domain": stored.get("detected_domain"),
            "objective": stored.get("objective"),
            "missing_fields": stored.get("missing_fields", []),
            "suggested_questions": stored.get("suggested_questions", []),
            "extracted_entities": stored.get("extracted_entities", {}),
            "confidence": stored.get("confidence"),
            "analyser_mode": stored.get("analyser_mode"),
            "run_id": existing.id,
            "deduped": True,
        }

    return {
        "detected_domain": intake_result.detected_domain,
        "objective": intake_result.objective,
        "missing_fields": intake_result.missing_fields,
        "suggested_questions": intake_result.suggested_questions,
        "extracted_entities": intake_result.extracted_entities,
        "confidence": intake_result.confidence,
        "analyser_mode": intake_result.analyser_mode,
        "run_id": run.id,
    }


@router.post(
    "/{project_id}/clarify",
    response_model=Dict[str, Any],
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_LLM))],
)
async def clarify_requirements(
    project_id: int,
    request: SpecClarifyRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Process clarification answers using Clarification Agent"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    run = None
    if request.run_id:
        run = await db.scalar(
            select(GenerationRun).where(
                GenerationRun.id == request.run_id,
                GenerationRun.project_id == project_id,
                GenerationRun.organization_id == current_user.organization_id,
            )
        )
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")
    # Merge order: stale intake entities first, then fresh stored answers win.
    # Previously request.current_intake overwrote run.clarification_json on key
    # collision, discarding prior LLM-derived answers.
    from cymatic_shared.agents.clarification_agent import normalize_answer_keys

    stored_answers = normalize_answer_keys(
        dict((run.clarification_json if run else {}) or {})
    )
    intake_entities = normalize_answer_keys(
        (request.current_intake or {}).get("extracted_entities", {}) or {}
    )
    # Drop boolean-only fallback artifacts (e.g. {"style": True}) that would
    # falsely mark required fields as answered.
    intake_entities = {k: v for k, v in intake_entities.items() if v is not True}
    current_answers = {**intake_entities, **stored_answers}
    new_answers = normalize_answer_keys(dict(request.answers or {}))

    # Domain reconciliation: prefer the LLM-detected domain stored on the run,
    # fall back to project.domain. Warn on mismatch (stale creation-time domain).
    detected_domain = None
    prompt_text = None
    objective_text = None
    if run and isinstance(run.intake_json, dict):
        detected_domain = run.intake_json.get("detected_domain")
        prompt_text = run.prompt or run.intake_json.get("objective")
        objective_text = run.intake_json.get("objective")
    domain = detected_domain or project.domain
    if detected_domain and detected_domain != project.domain:
        import structlog as _structlog

        _structlog.get_logger().warning(
            "clarify_domain_mismatch",
            project_domain=project.domain,
            detected_domain=detected_domain,
            run_id=run.id if run else None,
        )

    clarification_result = await _specs_ns.process_clarification_answers(
        domain=domain,
        current_answers=current_answers,
        new_answers=new_answers,
        prompt=prompt_text,
        objective=objective_text,
        intake_entities=intake_entities,
    )

    if run:
        run.clarification_json = copy.deepcopy(clarification_result.updated_fields)
        run.stage = (
            RunStage.SPEC
            if clarification_result.ready_for_generation
            else RunStage.CLARIFICATION
        )
        run.status = (
            RunStatus.READY_FOR_SPEC
            if clarification_result.ready_for_generation
            else RunStatus.NEEDS_CLARIFICATION
        )
        run.progress = 30 if clarification_result.ready_for_generation else 20
        # Per-run analyser trace: prompt -> entities -> grounded questions.
        # Stored inside intake_json (no migration needed) and readable via
        # GET generation-runs for debugging which path served this run.
        intake_snapshot = dict(run.intake_json or {})
        intake_snapshot["analyser_trace"] = {
            "intake_mode": intake_snapshot.get("analyser_mode", "unknown"),
            "clarify_mode": clarification_result.analyser_mode,
            "domain": domain,
            "questions": [
                {"field": q.field, "evidence_span": q.evidence_span}
                for q in clarification_result.questions
            ],
        }
        run.intake_json = intake_snapshot
        flag_modified(run, "intake_json")
        await db.commit()

    return {
        "updated_fields": copy.deepcopy(clarification_result.updated_fields),
        "ready_for_generation": clarification_result.ready_for_generation,
        "completion_percentage": clarification_result.completion_percentage,
        "analyser_mode": clarification_result.analyser_mode,
        "remaining_questions": [
            {
                "field": q.field,
                "question": q.question,
                "type": q.type,
                "options": q.options,
                "required": q.required,
                "evidence_span": q.evidence_span,
            }
            for q in clarification_result.questions
        ],
        "run_id": run.id if run else None,
    }


@router.post(
    "/{project_id}/clarify-with-state",
    response_model=Dict[str, Any],
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_LLM))],
)
async def clarify_with_state(
    project_id: int,
    request: ClarifyWithStateRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Process clarification with full intake state"""
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Use Clarification Agent with full state (same merge + domain rules as /clarify)
    from cymatic_shared.agents.clarification_agent import normalize_answer_keys as _norm

    _stored: Dict[str, Any] = {}
    _prompt: Optional[str] = None
    _objective: Optional[str] = None
    _detected: Optional[str] = None
    if request.run_id:
        _run = await db.scalar(
            select(GenerationRun).where(
                GenerationRun.id == request.run_id,
                GenerationRun.project_id == project_id,
                GenerationRun.organization_id == current_user.organization_id,
            )
        )
        if _run:
            _stored = _norm(dict(_run.clarification_json or {}))
            if isinstance(_run.intake_json, dict):
                _detected = _run.intake_json.get("detected_domain")
                _objective = _run.intake_json.get("objective")
            _prompt = _run.prompt
    _intake_entities = _norm(
        (request.current_intake or {}).get("extracted_entities", {}) or {}
    )
    _intake_entities = {k: v for k, v in _intake_entities.items() if v is not True}
    _current = {**_intake_entities, **_stored}
    _domain = _detected or project.domain
    clarification_result = await _specs_ns.process_clarification_answers(
        domain=_domain,
        current_answers=_current,
        new_answers=_norm(dict(request.answers or {})),
        prompt=_prompt,
        objective=_objective,
        intake_entities=_intake_entities,
    )

    if request.run_id:
        run = await db.scalar(
            select(GenerationRun).where(
                GenerationRun.id == request.run_id,
                GenerationRun.project_id == project_id,
                GenerationRun.organization_id == current_user.organization_id,
            )
        )
        if not run:
            raise HTTPException(status_code=404, detail="Generation run not found")
        run.clarification_json = copy.deepcopy(clarification_result.updated_fields)
        run.stage = (
            RunStage.SPEC
            if clarification_result.ready_for_generation
            else RunStage.CLARIFICATION
        )
        run.status = (
            RunStatus.READY_FOR_SPEC
            if clarification_result.ready_for_generation
            else RunStatus.NEEDS_CLARIFICATION
        )
        run.progress = 30 if clarification_result.ready_for_generation else 20
        intake_snapshot = dict(run.intake_json or {})
        intake_snapshot["analyser_trace"] = {
            "intake_mode": intake_snapshot.get("analyser_mode", "unknown"),
            "clarify_mode": clarification_result.analyser_mode,
            "domain": _domain,
            "questions": [
                {"field": q.field, "evidence_span": q.evidence_span}
                for q in clarification_result.questions
            ],
        }
        run.intake_json = intake_snapshot
        flag_modified(run, "intake_json")
        await db.commit()

    return {
        "updated_fields": copy.deepcopy(clarification_result.updated_fields),
        "ready_for_generation": clarification_result.ready_for_generation,
        "completion_percentage": clarification_result.completion_percentage,
        "analyser_mode": clarification_result.analyser_mode,
        "remaining_questions": [
            {
                "field": q.field,
                "question": q.question,
                "type": q.type,
                "options": q.options,
                "required": q.required,
                "evidence_span": q.evidence_span,
            }
            for q in clarification_result.questions
        ],
        "run_id": request.run_id,
    }
