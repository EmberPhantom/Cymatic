from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.dependencies import get_current_user, require_viewer, require_creator
from app.db.session import get_db
from app.models.project import Project
from app.models.stream_session import StreamSession
from app.models.runtime_event import RuntimeEvent
from app.models.user import User, UserRole

router = APIRouter()


class ProjectAnalytics(BaseModel):
    project_id: int
    total_sessions: int
    total_duration_seconds: int
    avg_session_duration_seconds: float
    unique_users: int
    events_by_type: Dict[str, int]
    completion_rate: float


class SessionAnalytics(BaseModel):
    session_id: int
    duration_seconds: int
    events_count: int
    events_by_type: Dict[str, int]
    navigation_path: List[str]
    copilot_interactions: int
    voice_interactions: int


class OrganizationAnalytics(BaseModel):
    total_projects: int
    total_sessions: int
    total_users: int
    total_duration_seconds: int
    projects_by_domain: Dict[str, int]
    sessions_by_status: Dict[str, int]


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
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get sessions
    sessions_result = await db.execute(
        select(StreamSession).where(StreamSession.project_id == project_id)
    )
    sessions = sessions_result.scalars().all()
    
    # Get events
    session_ids = [s.id for s in sessions]
    events_by_type = {}
    if session_ids:
        events_result = await db.execute(
            select(RuntimeEvent.event_type, func.count(RuntimeEvent.id))
            .where(RuntimeEvent.stream_session_id.in_(session_ids))
            .group_by(RuntimeEvent.event_type)
        )
        events_by_type = dict(events_result.all())
    
    total_duration = sum(
        (s.ended_at - s.started_at).total_seconds() 
        for s in sessions if s.ended_at
    )
    
    return ProjectAnalytics(
        project_id=project_id,
        total_sessions=len(sessions),
        total_duration_seconds=int(total_duration),
        avg_session_duration_seconds=total_duration / len(sessions) if sessions else 0,
        unique_users=len(set(s.user_id for s in sessions)),
        events_by_type=events_by_type,
        completion_rate=0.0,
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
    
    # Get events
    events_result = await db.execute(
        select(RuntimeEvent).where(RuntimeEvent.stream_session_id == session_id)
    )
    events = events_result.scalars().all()
    
    events_by_type = {}
    navigation_path = []
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
    
    duration = 0
    if session.ended_at:
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
    projects_by_domain = dict(domain_result.all())
    
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
    sessions_by_status = dict(status_result.all())
    
    # Total users
    users_result = await db.execute(
        select(func.count(User.id)).where(User.organization_id == org_id)
    )
    total_users = users_result.scalar() or 0
    
    # Total duration
    duration_result = await db.execute(
        select(func.sum(
            func.extract('epoch', StreamSession.ended_at) - func.extract('epoch', StreamSession.started_at)
        ))
        .join(Project, StreamSession.project_id == Project.id)
        .where(Project.organization_id == org_id)
        .where(StreamSession.ended_at.isnot(None))
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