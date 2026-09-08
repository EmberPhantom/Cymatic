from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.dependencies import require_viewer, require_admin
from app.db.session import get_db
from app.models.project import Project
from app.models.stream_session import StreamSession
from app.models.runtime_event import RuntimeEvent
from app.models.user import User

router = APIRouter()


class ProjectAnalytics(BaseModel):
    project_id: int
    total_sessions: int
    total_duration_seconds: int
    avg_session_duration_seconds: float
    unique_users: int
    events_by_type: dict[str, int]
    completion_rate: float


class SessionAnalytics(BaseModel):
    session_id: int
    duration_seconds: int
    events_count: int
    events_by_type: dict[str, int]
    navigation_path: list[str]
    copilot_interactions: int
    voice_interactions: int


class OrganizationAnalytics(BaseModel):
    total_projects: int
    total_sessions: int
    total_users: int
    total_duration_seconds: int
    projects_by_domain: dict[str, int]
    sessions_by_status: dict[str, int]


@router.get("/projects/{project_id}", response_model=ProjectAnalytics)
async def get_project_analytics(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
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

    # Aggregate sessions via SQL to avoid N+1 / loading all rows
    total_sessions_res = await db.execute(
        select(func.count(StreamSession.id)).where(StreamSession.project_id == project_id)
    )
    total_sessions = int(total_sessions_res.scalar() or 0)

    unique_users_res = await db.execute(
        select(func.count(func.distinct(StreamSession.user_id))).where(
            StreamSession.project_id == project_id
        )
    )
    unique_users = int(unique_users_res.scalar() or 0)

    duration_res = await db.execute(
        select(
            func.sum(
                func.extract("epoch", StreamSession.ended_at)
                - func.extract("epoch", StreamSession.started_at)
            )
        )
        .where(StreamSession.project_id == project_id)
        .where(StreamSession.ended_at.isnot(None))
        .where(StreamSession.started_at.isnot(None))
    )
    total_duration_raw = duration_res.scalar()
    total_duration = int(total_duration_raw or 0)
    avg_duration = (total_duration / total_sessions) if total_sessions else 0

    # Events aggregate via join (avoid IN with large list and fix column name session_id)
    events_result = await db.execute(
        select(RuntimeEvent.event_type, func.count(RuntimeEvent.id))
        .join(StreamSession, RuntimeEvent.session_id == StreamSession.id)
        .where(StreamSession.project_id == project_id)
        .group_by(RuntimeEvent.event_type)
    )
    events_by_type: dict[str, int] = {row[0]: row[1] for row in events_result.all()}

    completed_sessions_res = await db.execute(
        select(func.count(func.distinct(RuntimeEvent.session_id)))
        .join(StreamSession, RuntimeEvent.session_id == StreamSession.id)
        .where(StreamSession.project_id == project_id)
        .where(
            RuntimeEvent.event_type.in_(
                ["tour_completed", "session_completed", "walkthrough_completed"]
            )
        )
    )
    completed_sessions = int(completed_sessions_res.scalar() or 0)
    completion_rate = (
        completed_sessions / total_sessions if total_sessions else 0.0
    )

    return ProjectAnalytics(
        project_id=project_id,
        total_sessions=total_sessions,
        total_duration_seconds=total_duration,
        avg_session_duration_seconds=avg_duration,
        unique_users=unique_users,
        events_by_type=events_by_type,
        completion_rate=completion_rate,
    )


@router.get("/sessions/{session_id}", response_model=SessionAnalytics)
async def get_session_analytics(
    session_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(StreamSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Verify org access
    project_result = await db.execute(
        select(Project).where(Project.id == session.project_id)
    )
    project = project_result.scalar_one_or_none()
    if not project or project.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Get events (fix column name session_id not stream_session_id)
    events_result = await db.execute(
        select(RuntimeEvent).where(RuntimeEvent.session_id == session_id)
    )
    events = events_result.scalars().all()

    events_by_type: dict[str, int] = {}
    navigation_path: list[str] = []
    copilot_interactions = 0
    voice_interactions = 0

    for event in events:
        events_by_type[event.event_type] = events_by_type.get(event.event_type, 0) + 1
        if event.event_type == "navigation_point_changed":
            nav_data = event.payload_json
            if "point_id" in nav_data:
                navigation_path.append(nav_data["point_id"])
        elif event.event_type == "copilot_message_sent":
            copilot_interactions += 1
        elif event.event_type in ["voice_session_started", "voice_session_completed"]:
            voice_interactions += 1

    duration: float = 0
    if session.ended_at and session.started_at:
        duration = (session.ended_at - session.started_at).total_seconds()

    return SessionAnalytics(
        session_id=session_id,
        duration_seconds=int(duration),
        events_count=len(events),
        events_by_type=events_by_type,
        navigation_path=navigation_path,
        copilot_interactions=copilot_interactions,
        voice_interactions=voice_interactions,
    )


@router.get("/organization", response_model=OrganizationAnalytics)
async def get_organization_analytics(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    org_id = current_user.organization_id

    # Total projects
    projects_result = await db.execute(
        select(func.count(Project.id)).where(Project.organization_id == org_id)
    )
    total_projects = projects_result.scalar() or 0

    # Projects by domain
    domain_result = await db.execute(
        select(Project.domain, func.count(Project.id))
        .where(Project.organization_id == org_id)
        .group_by(Project.domain)
    )
    projects_by_domain: dict[str, int] = {row[0]: row[1] for row in domain_result.all()}

    # Total sessions
    sessions_result = await db.execute(
        select(func.count(StreamSession.id))
        .join(Project, StreamSession.project_id == Project.id)
        .where(Project.organization_id == org_id)
    )
    total_sessions = sessions_result.scalar() or 0

    # Sessions by status
    status_result = await db.execute(
        select(StreamSession.status, func.count(StreamSession.id))
        .join(Project, StreamSession.project_id == Project.id)
        .where(Project.organization_id == org_id)
        .group_by(StreamSession.status)
    )
    sessions_by_status: dict[str, int] = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): int(row[1])
        for row in status_result.all()
    }

    # Total users
    users_result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org_id)
    )
    total_users = users_result.scalar() or 0

    # Total duration
    duration_result = await db.execute(
        select(
            func.sum(
                func.extract("epoch", StreamSession.ended_at)
                - func.extract("epoch", StreamSession.started_at)
            )
        )
        .join(Project, StreamSession.project_id == Project.id)
        .where(Project.organization_id == org_id)
        .where(StreamSession.ended_at.isnot(None))
        .where(StreamSession.started_at.isnot(None))
    )
    total_duration = int(duration_result.scalar() or 0)

    return OrganizationAnalytics(
        total_projects=total_projects,
        total_sessions=total_sessions,
        total_users=total_users,
        total_duration_seconds=total_duration,
        projects_by_domain=projects_by_domain,
        sessions_by_status=sessions_by_status,
    )
