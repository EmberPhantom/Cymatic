"""Worker MinIO client - configured instance for worker service."""
from cymatic_shared.services.minio_client import MinIOClient
from app.core.config import get_settings

settings = get_settings()

minio_client = MinIOClient(
    endpoint=settings.S3_ENDPOINT,
    access_key=settings.S3_ACCESS_KEY,
    secret_key=settings.S3_SECRET_KEY,
    bucket_name=settings.S3_BUCKET_NAME,
    region=settings.S3_REGION,
)
