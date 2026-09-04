from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
from datetime import timedelta
from app.core.dependencies import require_creator, require_admin, require_viewer
from app.db.session import get_db
from app.models.asset import Asset, AssetType, AssetStatus
from app.models.project import Project
from app.models.user import User
from app.services.minio_client import (
    get_minio_client,
    get_asset_storage_key,
    get_asset_presigned_download_url,
)

router = APIRouter()


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    project_id: Optional[int]
    type: str
    storage_key: str
    status: str
    metadata_json: dict
    created_at: datetime


class AssetUploadInit(BaseModel):
    filename: str
    content_type: str
    type: str
    project_id: Optional[int] = None


class AssetUploadInitResponse(BaseModel):
    upload_url: str
    asset_id: int
    storage_key: str


class AssetUploadComplete(BaseModel):
    asset_id: int
    size: Optional[int] = None


@router.post("/upload/init", response_model=AssetUploadInitResponse)
async def init_upload(
    upload_data: AssetUploadInit,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Initialize a presigned upload URL for MinIO"""
    try:
        asset_type = AssetType(upload_data.type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid asset type")

    if upload_data.project_id:
        result = await db.execute(
            select(Project).where(
                Project.id == upload_data.project_id,
                Project.organization_id == current_user.organization_id,
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    # Generate storage key
    storage_key = get_asset_storage_key(
        current_user.organization_id, upload_data.project_id, upload_data.filename
    )

    # Get presigned upload URL
    upload_url = get_minio_client().get_presigned_put_url(
        storage_key, expires=timedelta(hours=1)
    )

    # Create asset record
    asset = Asset(
        organization_id=current_user.organization_id,
        project_id=upload_data.project_id,
        type=asset_type,
        storage_key=storage_key,
        status=AssetStatus.UPLOADING,
        metadata_json={
            "original_filename": upload_data.filename,
            "content_type": upload_data.content_type,
        },
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    return AssetUploadInitResponse(
        upload_url=upload_url,
        asset_id=asset.id,
        storage_key=storage_key,
    )


@router.post("/upload/complete", response_model=AssetResponse)
async def complete_upload(
    complete_data: AssetUploadComplete,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Mark upload as complete and verify in MinIO"""
    result = await db.execute(
        select(Asset).where(
            Asset.id == complete_data.asset_id,
            Asset.organization_id == current_user.organization_id,
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Verify object exists in MinIO
    if not get_minio_client().object_exists(asset.storage_key):
        raise HTTPException(status_code=400, detail="Object not found in storage")

    # Get object info
    info = get_minio_client().get_object_info(asset.storage_key)
    asset.metadata_json.update(
        {
            "size": info["size"],
            "etag": info["etag"],
            "content_type": info["content_type"],
        }
    )

    asset.status = AssetStatus.READY
    await db.commit()
    await db.refresh(asset)

    # Queue asset processing (thumbnails, LODs, etc.)
    from app.core.queue import job_queue, Job, JobPriority

    job = Job(
        id=f"asset_{asset.id}_{int(asyncio.get_event_loop().time())}",
        type="process_asset",
        payload={"asset_id": asset.id},
        priority=JobPriority.NORMAL,
    )
    await job_queue.enqueue(job, "asset")

    return asset


@router.get("", response_model=List[AssetResponse])
async def list_assets(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    project_id: Optional[int] = None,
    type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
):
    query = select(Asset).where(Asset.organization_id == current_user.organization_id)

    if project_id:
        query = query.where(Asset.project_id == project_id)
    if type:
        try:
            asset_type = AssetType(type)
            query = query.where(Asset.type == asset_type)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid asset type")

    query = query.offset(skip).limit(limit).order_by(Asset.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/projects/{project_id}", response_model=List[AssetResponse])
async def list_project_assets(
    project_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    result = await db.execute(
        select(Asset)
        .where(
            Asset.project_id == project_id,
            Asset.organization_id == current_user.organization_id,
        )
        .order_by(Asset.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id, Asset.organization_id == current_user.organization_id
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("/{asset_id}/download")
async def get_download_url(
    asset_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    expires_hours: int = 1,
):
    """Get presigned download URL for asset"""
    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id, Asset.organization_id == current_user.organization_id
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    url = get_asset_presigned_download_url(asset.storage_key, expires_hours)
    return {"download_url": url, "expires_hours": expires_hours}


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(
            Asset.id == asset_id, Asset.organization_id == current_user.organization_id
        )
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Delete from MinIO
    get_minio_client().delete_object(asset.storage_key)

    await db.delete(asset)
    await db.commit()
