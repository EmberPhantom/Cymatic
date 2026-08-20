"""Shared MinIO client for object storage operations."""
import io
from datetime import timedelta
from typing import Optional
from minio import Minio
from minio.error import S3Error
import structlog

logger = structlog.get_logger()


class MinIOClient:
    """MinIO client wrapper for uploads/downloads."""

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket_name: str, region: str = "us-east-1"):
        self.client = Minio(
            endpoint.replace("http://", "").replace("https://", ""),
            access_key=access_key,
            secret_key=secret_key,
            secure=endpoint.startswith("https"),
            region=region,
        )
        self.bucket_name = bucket_name
        self.region = region
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name, location=self.region)
                logger.info("bucket_created", bucket=self.bucket_name)
        except S3Error as e:
            logger.error("bucket_creation_failed", bucket=self.bucket_name, error=str(e))
            raise

    def upload_data(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict = None,
    ) -> str:
        try:
            data_stream = io.BytesIO(data)
            self.client.put_object(
                self.bucket_name,
                object_name,
                data_stream,
                length=len(data),
                content_type=content_type,
                metadata=metadata or {},
            )
            logger.info("data_uploaded", object=object_name, size=len(data))
            return object_name
        except S3Error as e:
            logger.error("data_upload_failed", object=object_name, error=str(e))
            raise

    def download_data(self, object_name: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error("data_download_failed", object=object_name, error=str(e))
            raise

    def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        try:
            return self.client.presigned_get_object(
                self.bucket_name, object_name, expires=expires
            )
        except S3Error as e:
            logger.error("presigned_url_failed", object=object_name, error=str(e))
            raise

    def object_exists(self, object_name: str) -> bool:
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False
