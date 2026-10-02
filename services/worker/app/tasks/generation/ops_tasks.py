"""Worker asset/analytics task handlers (split from tasks/generation.py, no logic change)."""

import structlog

from app.core.queue import register_job_handler
from cymatic_shared.models import Asset, AssetStatus
from app.services.minio_client import get_minio_client

from sqlalchemy import select
from minio.error import S3Error

# DB sessions resolve via the generation package namespace so tests
# can patch app.tasks.generation.AsyncSessionLocal.
from app.tasks import generation as _gen

logger = structlog.get_logger()


@register_job_handler("process_asset")
async def process_asset_task(payload: dict) -> dict:
    """Process uploaded asset based on type: extract metadata from MinIO, validate, mark ready."""
    asset_id = payload.get("asset_id")

    logger.info("process_asset_started", asset_id=asset_id)

    async with _gen.AsyncSessionLocal() as db:
        result = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = result.scalar_one_or_none()

        if not asset:
            raise ValueError(f"Asset {asset_id} not found")

        asset.status = AssetStatus.PROCESSING
        asset.metadata_json = asset.metadata_json or {}
        await db.commit()

        asset_type = (
            asset.type.value if hasattr(asset.type, "value") else str(asset.type)
        )
        file_ext = (
            asset.filename.rsplit(".", 1)[-1].lower()
            if asset.filename and "." in asset.filename
            else "unknown"
        )

        try:
            info = get_minio_client().get_object_info(asset.storage_key)

            asset.metadata_json["processed"] = True
            asset.metadata_json["size"] = info.get("size")
            asset.metadata_json["etag"] = info.get("etag")
            asset.metadata_json["content_type"] = info.get("content_type")
            asset.metadata_json["format"] = file_ext

            if asset_type == "image":
                asset.metadata_json["note"] = (
                    "Image metadata extracted; thumbnail generation requires Pillow (not yet available)"
                )

            elif asset_type == "model_3d":
                asset.metadata_json["note"] = (
                    "3D model metadata extracted; LOD generation requires mesh processing (not yet available)"
                )

            elif asset_type == "audio":
                asset.metadata_json["note"] = "Audio stored as-is for MVP"

            else:
                asset.metadata_json["note"] = (
                    f"No specific processing for type '{asset_type}'"
                )

            asset.status = AssetStatus.READY
            await db.commit()

            logger.info(
                "process_asset_completed",
                asset_id=asset_id,
                asset_type=asset_type,
                size=info.get("size"),
            )
            return {
                "asset_id": asset_id,
                "status": "ready",
                "type": asset_type,
                "size": info.get("size"),
            }

        except (S3Error, OSError) as e:
            asset.status = AssetStatus.FAILED
            asset.metadata_json["error"] = str(e)
            await db.commit()
            logger.error("process_asset_failed", asset_id=asset_id, error=str(e))
            raise


@register_job_handler("analytics_aggregation")
async def analytics_aggregation_task(payload: dict) -> dict:
    """Aggregate analytics data for a project: session counts, event totals, durations."""
    project_id = payload.get("project_id")

    logger.info("analytics_aggregation_started", project_id=project_id)

    from cymatic_shared.models import StreamSession, StreamSessionStatus
    from cymatic_shared.models import RuntimeEvent

    async with _gen.AsyncSessionLocal() as db:
        sessions_result = await db.execute(
            select(StreamSession).where(StreamSession.project_id == project_id)
        )
        sessions = sessions_result.scalars().all()

        total_sessions = len(sessions)
        active_sessions = sum(
            1 for s in sessions if s.status == StreamSessionStatus.ACTIVE
        )
        completed_sessions = sum(
            1 for s in sessions if s.status == StreamSessionStatus.DISCONNECTED
        )

        total_duration_seconds = 0.0
        for s in sessions:
            if s.started_at and s.ended_at:
                total_duration_seconds += (s.ended_at - s.started_at).total_seconds()

        session_ids = [s.id for s in sessions]
        if session_ids:
            events_result = await db.execute(
                select(RuntimeEvent).where(RuntimeEvent.session_id.in_(session_ids))
            )
            events = events_result.scalars().all()
        else:
            events = []

        event_counts: dict[str, int] = {}
        total_events = len(events)
        for event in events:
            event_counts[event.event_type] = event_counts.get(event.event_type, 0) + 1

        aggregated = {
            "project_id": project_id,
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "completed_sessions": completed_sessions,
            "total_duration_seconds": round(total_duration_seconds, 2),
            "total_events": total_events,
            "event_counts_by_type": event_counts,
        }

        logger.info(
            "analytics_aggregation_completed",
            project_id=project_id,
            total_sessions=total_sessions,
            total_events=total_events,
        )

        return aggregated
