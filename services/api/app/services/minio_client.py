"""MinIO / S3-compatible object storage - re-exported from shared package.

Single source: cymatic_shared.services.minio_client (pooled full client).
This module keeps the settings-bound singleton plus the org/project key
conventions used across api endpoints.
"""
from datetime import timedelta

from cymatic_shared.services.minio_client import MinIOClient  # noqa: F401
from app.core.config import get_settings

settings = get_settings()

_minio_client_instance: "MinIOClient | None" = None


def get_minio_client() -> MinIOClient:
    global _minio_client_instance
    if _minio_client_instance is None:
        _minio_client_instance = MinIOClient(
            settings.S3_ENDPOINT,
            settings.S3_ACCESS_KEY,
            settings.S3_SECRET_KEY,
            settings.S3_BUCKET_NAME,
            settings.S3_REGION,
        )
    return _minio_client_instance


def get_asset_storage_key(organization_id: int, project_id: int | None, filename: str) -> str:
    """Generate standardized storage key for assets."""
    if project_id:
        return f"orgs/{organization_id}/projects/{project_id}/assets/{filename}"
    return f"orgs/{organization_id}/assets/{filename}"


def get_scene_package_key(organization_id: int, project_id: int, spec_id: int, version: int) -> str:
    """Generate storage key for scene packages."""
    return f"orgs/{organization_id}/projects/{project_id}/scenes/spec_{spec_id}_v{version}.cymatic"


def get_asset_presigned_upload_url(
    organization_id: int, project_id: int | None, filename: str, expires_hours: int = 1
) -> tuple[str, str]:
    """Get presigned upload URL and storage key for an asset."""
    storage_key = get_asset_storage_key(organization_id, project_id, filename)
    url = get_minio_client().get_presigned_put_url(
        storage_key, expires=timedelta(hours=expires_hours)
    )
    return url, storage_key


def get_asset_presigned_download_url(storage_key: str, expires_hours: int = 1) -> str:
    """Get presigned download URL for an asset."""
    return get_minio_client().get_presigned_url(
        storage_key, expires=timedelta(hours=expires_hours)
    )
