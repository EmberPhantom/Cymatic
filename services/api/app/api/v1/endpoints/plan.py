"""Planning agent endpoints: build, fetch, and approve planning sheets.

A planning sheet is the frozen, reviewable output of intake + clarification
(+ research in Phase 3). Only APPROVED sheets feed the generation agent.
"""

import copy
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin, require_creator, require_viewer
from app.db.session import get_db
from app.models.generation_run import GenerationRun
from app.models.planning_sheet import PlanningSheet as PlanningSheetModel, SheetStatus
from app.models.project import Project
from app.models.user import User
from cymatic_shared.schemas.planning_sheet import PlanningSheet, PlanSpace

router = APIRouter()


class PlanBuildRequest(BaseModel):
    run_id: str


class SheetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version: int
    status: str
    run_id: Optional[str] = None
    sheet: Dict[str, Any]


def _clean_entities(*sources: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge entity dicts; clarification wins. Drop boolean-only artifacts."""
    merged: Dict[str, Any] = {}
    for src in sources:
        for k, v in (src or {}).items():
            if v is True:
                continue
            merged[k] = copy.deepcopy(v)
    return merged


def _split_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip().strip(".") for v in value if str(v).strip()]
    if isinstance(value, str):
        return [
            p.strip().strip(".")
            for p in value.replace(";", ",").split(",")
            if p.strip()
        ]
    return []


def build_sheet_payload(
    *,
    objective: str,
    domain: str,
    entities: Dict[str, Any],
    missing_fields: List[str],
    analyser_mode: str,
) -> PlanningSheet:
    """Translate intake/clarification evidence into a typed planning sheet.

    Only evidence-backed content: POIs split from key_pois, room count from
    bedrooms, style/material/lighting fragments. No invented features.
    """
    spaces: List[PlanSpace] = []
    domain = domain if domain in ("real_estate", "heritage") else "real_estate"
    kind = "poi" if domain == "heritage" else "room"

    for i, poi in enumerate(_split_list(entities.get("key_pois"))[:12]):
        spaces.append(PlanSpace(id=f"space_{i + 1}", kind=kind, name=poi))

    bedrooms = entities.get("bedrooms")
    try:
        count = (
            int(bedrooms)
            if isinstance(bedrooms, (int, float, str))
            and str(bedrooms).strip().isdigit()
            else 0
        )
    except (TypeError, ValueError):
        count = 0
    if domain == "real_estate" and count > 0:
        for i in range(min(count, 12)):
            spaces.append(
                PlanSpace(id=f"space_room_{i + 1}", kind="room", name=f"Room {i + 1}")
            )

    style: Dict[str, str] = {}
    for field in (
        "style",
        "historical_period",
        "focus",
        "lighting_preference",
        "budget",
        "scale",
        "indoor_outdoor",
    ):
        value = entities.get(field)
        if isinstance(value, str) and value.strip():
            style[field] = value.strip()
        elif isinstance(value, (int, float)):
            style[field] = str(value)

    constraints: Dict[str, Any] = {}
    for field in (
        "narration",
        "languages",
        "furnished",
        "square_footage",
        "floors",
        "site_type",
    ):
        if field in entities:
            constraints[field] = entities[field]

    return PlanningSheet(
        objective=objective,
        domain=domain,  # type: ignore[arg-type]
        spaces=spaces,
        style=style,
        constraints=constraints,
        open_questions=list(missing_fields or []),
        research_refs=[],
        analyser_mode=analyser_mode or "llm",
    )


async def _get_project(project_id: int, user: User, db: AsyncSession) -> Project:
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _sheet_to_response(sheet: PlanningSheetModel) -> SheetResponse:
    return SheetResponse(
        id=sheet.id,
        project_id=sheet.project_id,
        version=sheet.version,
        status=sheet.status.value
        if hasattr(sheet.status, "value")
        else str(sheet.status),
        run_id=sheet.run_id,
        sheet=sheet.payload_json if isinstance(sheet.payload_json, dict) else {},
    )


@router.post("/{project_id}/plan", response_model=SheetResponse)
async def build_plan(
    project_id: int,
    request: PlanBuildRequest,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Build a draft planning sheet from a generation run's intake/clarify."""
    project = await _get_project(project_id, current_user, db)
    run = await db.scalar(
        select(GenerationRun).where(
            GenerationRun.id == request.run_id,
            GenerationRun.project_id == project_id,
            GenerationRun.organization_id == current_user.organization_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Generation run not found")

    intake = run.intake_json if isinstance(run.intake_json, dict) else {}
    entities = _clean_entities(
        intake.get("extracted_entities") if isinstance(intake, dict) else None,
        run.clarification_json,
    )
    missing = set()
    for key in ("missing_fields",):
        values = intake.get(key) if isinstance(intake, dict) else None
        if isinstance(values, list):
            missing.update(str(v) for v in values)
    missing.difference_update(entities.keys())

    sheet = build_sheet_payload(
        objective=run.prompt,
        domain=(intake.get("detected_domain") if isinstance(intake, dict) else None)
        or project.domain,
        entities=entities,
        missing_fields=sorted(missing),
        analyser_mode=(
            intake.get("analyser_mode") if isinstance(intake, dict) else None
        )
        or "llm",
    )

    version = await db.scalar(
        select(func.coalesce(func.max(PlanningSheetModel.version), 0) + 1).where(
            PlanningSheetModel.project_id == project_id
        )
    )
    record = PlanningSheetModel(
        project_id=project_id,
        organization_id=project.organization_id,
        run_id=run.id,
        version=version,
        payload_json=sheet.model_dump(mode="json"),
        status=SheetStatus.DRAFT,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return _sheet_to_response(record)


@router.get("/{project_id}/plan", response_model=SheetResponse)
async def get_latest_plan(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Fetch the latest planning sheet (any status) for a project."""
    await _get_project(project_id, current_user, db)
    sheet = await db.scalar(
        select(PlanningSheetModel)
        .where(PlanningSheetModel.project_id == project_id)
        .order_by(PlanningSheetModel.version.desc())
    )
    if not sheet:
        raise HTTPException(
            status_code=404, detail="No planning sheet for this project"
        )
    return _sheet_to_response(sheet)


@router.post("/{project_id}/plan/{sheet_id}/approve", response_model=SheetResponse)
async def approve_plan(
    project_id: int,
    sheet_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Approve a sheet version; supersedes other approved versions."""
    await _get_project(project_id, current_user, db)
    sheet = await db.scalar(
        select(PlanningSheetModel).where(
            PlanningSheetModel.id == sheet_id,
            PlanningSheetModel.project_id == project_id,
        )
    )
    if not sheet:
        raise HTTPException(status_code=404, detail="Planning sheet not found")

    others = (
        await db.execute(
            select(PlanningSheetModel).where(
                PlanningSheetModel.project_id == project_id,
                PlanningSheetModel.status == SheetStatus.APPROVED,
                PlanningSheetModel.id != sheet_id,
            )
        )
    ).scalars()
    for other in others:
        other.status = SheetStatus.SUPERSEDED
    sheet.status = SheetStatus.APPROVED
    await db.commit()
    await db.refresh(sheet)
    return _sheet_to_response(sheet)
