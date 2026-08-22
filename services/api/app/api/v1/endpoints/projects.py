from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.dependencies import get_current_user, require_creator, require_admin
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.user import User, UserRole

router = APIRouter()

VALID_STATUS_TRANSITIONS = {
    ProjectStatus.DRAFT: {ProjectStatus.SPEC_GENERATING, ProjectStatus.FAILED},
    ProjectStatus.SPEC_GENERATING: {ProjectStatus.SPEC_READY, ProjectStatus.FAILED},
    ProjectStatus.SPEC_READY: {ProjectStatus.SCENE_GENERATING, ProjectStatus.FAILED},
    ProjectStatus.SCENE_GENERATING: {ProjectStatus.SCENE_READY, ProjectStatus.FAILED},
    ProjectStatus.SCENE_READY: {ProjectStatus.PUBLISHED, ProjectStatus.FAILED},
    ProjectStatus.PUBLISHED: set(),
    ProjectStatus.FAILED: {ProjectStatus.DRAFT},
}


class ProjectBase(BaseModel):
    name: str
    domain: str  # real_estate, heritage
    category: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    domain: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None


class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    status: str
    created_by: int
    created_at: datetime
    updated_at: Optional[datetime] = None


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    result = await db.execute(
        select(Project)
        .where(Project.organization_id == current_user.organization_id)
        .offset(skip).limit(limit)
        .order_by(Project.created_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreate,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    valid_domains = ["real_estate", "heritage"]
    if project_data.domain not in valid_domains:
        raise HTTPException(status_code=400, detail=f"Invalid domain. Must be one of: {valid_domains}")
    
    project = Project(
        name=project_data.name,
        domain=project_data.domain,
        category=project_data.category,
        organization_id=current_user.organization_id,
        created_by=current_user.id,
        status=ProjectStatus.DRAFT,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    project_update: ProjectUpdate,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project_update.name is not None:
        project.name = project_update.name
    if project_update.domain is not None:
        valid_domains = ["real_estate", "heritage"]
        if project_update.domain not in valid_domains:
            raise HTTPException(status_code=400, detail=f"Invalid domain. Must be one of: {valid_domains}")
        project.domain = project_update.domain
    if project_update.category is not None:
        project.category = project_update.category
    if project_update.status is not None:
        try:
            new_status = ProjectStatus(project_update.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
        current_status = project.status
        allowed = VALID_STATUS_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot transition from '{current_status.value}' to '{new_status.value}'",
            )
        project.status = new_status
    
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    await db.delete(project)
    await db.commit()