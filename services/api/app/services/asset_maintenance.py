"""Maintenance sweepers for orphan storage rows.

Single recurring-maintenance home for the API: startup (see app.main lifespan)
and the admin sweep endpoint in assets.py both call into here so the cutoff
and best-effort storage semantics stay in one place.
"""

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus
from app.services.minio_client import get_minio_client

logger = structlog.get_logger()


async def sweep_stale_uploading_assets(
    db: AsyncSession,
    older_than_hours: int = 24,
    limit: int = 100,
) -> int:
    """Delete UPLOADING assets abandoned before the cutoff.

    Rows are committed by init_upload before the client PUTs to MinIO, so a
    client that never completes leaves an orphan DB row (and possibly an
    orphan/partial MinIO object). Rows older than ``older_than_hours``
    (compared on ``created_at``) are removed; their MinIO objects are deleted
    best-effort — storage failures never block the DB cleanup.
    Returns the number of rows swept. Bounded by ``limit`` per run.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    rows = (
        (
            await db.execute(
                select(Asset)
                .where(
                    Asset.status == AssetStatus.UPLOADING,
                    Asset.created_at < cutoff,
                )
                .order_by(Asset.created_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    swept = 0
    for asset in rows:
        try:
            get_minio_client().delete_object(asset.storage_key)
        except Exception as e:
            logger.warning(
                "stale_upload_storage_delete_failed",
                asset_id=asset.id,
                storage_key=asset.storage_key,
                error=str(e),
            )
        await db.delete(asset)
        swept += 1
    if swept:
        await db.commit()
        logger.info(
            "stale_uploads_swept", swept=swept, older_than_hours=older_than_hours
        )
    return swept
