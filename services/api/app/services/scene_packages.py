"""Lookup helpers for a project's latest ready scene package.

Shared by the streaming session flow (presigned URL, for the Unity render
server) and the mobile browser viewer flow (proxied JSON body) so both read
the same "latest ready ScenePackage for a project" query instead of each
maintaining their own copy.
"""

import json
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scene_package import ScenePackage
from app.services.minio_client import get_minio_client

logger = structlog.get_logger()


class ScenePackageUnavailable(Exception):
    """A ready package record exists but storage/fetch failed.

    Distinct from "no package yet" (helpers return None) so callers can
    answer 503 instead of 404/null.
    """


async def get_latest_ready_scene_package(
    db: AsyncSession, project_id: int
) -> Optional[ScenePackage]:
    return await db.scalar(
        select(ScenePackage)
        .where(ScenePackage.project_id == project_id, ScenePackage.status == "ready")
        .order_by(ScenePackage.id.desc())
    )


async def get_latest_scene_package_url(
    db: AsyncSession, project_id: int
) -> Optional[str]:
    """Presigned download URL for a project's latest ready scene package, if any."""
    scene_pkg = await get_latest_ready_scene_package(db, project_id)
    if scene_pkg is None:
        return None
    try:
        return get_minio_client().get_presigned_url(scene_pkg.storage_key)
    except ScenePackageUnavailable:
        raise
    except Exception as e:
        # Any storage/transport failure (S3Error, urllib3 retry errors on
        # host-down, decode errors) means "package exists but unreadable".
        logger.error(
            "scene_package_presign_failed", project_id=project_id, error=str(e)
        )
        raise ScenePackageUnavailable(str(e)) from e


async def get_latest_scene_package_json(
    db: AsyncSession, project_id: int
) -> Optional[dict[str, Any]]:
    """The parsed cymatic_v1 scene package body for a project, fetched server-side
    from MinIO. Used by the mobile viewer so browsers never need direct MinIO
    access (no bucket CORS policy exists today)."""
    scene_pkg = await get_latest_ready_scene_package(db, project_id)
    if scene_pkg is None:
        return None
    try:
        raw = get_minio_client().download_data(scene_pkg.storage_key)
        return json.loads(raw)
    except ScenePackageUnavailable:
        raise
    except Exception as e:
        logger.error("scene_package_fetch_failed", project_id=project_id, error=str(e))
        raise ScenePackageUnavailable(str(e)) from e
