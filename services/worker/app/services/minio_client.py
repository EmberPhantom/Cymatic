"""Worker MinIO client - lazy-loaded singleton."""
from cymatic_shared.services.minio_client import MinIOClient
from app.core.config import get_settings
import structlog

logger = structlog.get_logger()
_settings = get_settings()
_minio_client: MinIOClient | None = None


def get_minio_client() -> MinIOClient:
    global _minio_client
    if _minio_client is None:
        logger.info("minio_client_initializing", endpoint=_settings.S3_ENDPOINT)
        _minio_client = MinIOClient(
            endpoint=_settings.S3_ENDPOINT,
            access_key=_settings.S3_ACCESS_KEY,
            secret_key=_settings.S3_SECRET_KEY,
            bucket_name=_settings.S3_BUCKET_NAME,
            region=_settings.S3_REGION,
        )
    return _minio_client
