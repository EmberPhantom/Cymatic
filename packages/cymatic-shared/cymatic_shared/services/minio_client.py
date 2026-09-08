"""Shared MinIO client for object storage operations."""
import asyncio
import io
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
import structlog

logger = structlog.get_logger()


class MinIOClient:
    """MinIO client wrapper for uploads/downloads.

    Sync methods are retained for backward compat but delegate to threadpool
    when called from async context via `*_async` variants to avoid blocking the event loop.
    """

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
        except OSError as e:
            logger.warning("bucket_check_deferred", bucket=self.bucket_name, error=str(e))

    # ---- Sync core (blocking) ----
    def _upload_sync(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> str:
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

    def _download_sync(self, object_name: str) -> bytes:
        response = self.client.get_object(self.bucket_name, object_name)
        try:
            data = response.read()
            return data
        finally:
            response.close()
            response.release_conn()

    def upload_data(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> str:
        """Sync upload (blocks). Prefer `upload_data_async` in async code."""
        try:
            return self._upload_sync(object_name, data, content_type, metadata)
        except S3Error as e:
            logger.error("data_upload_failed", object=object_name, error=str(e))
            raise

    def download_data(self, object_name: str) -> bytes:
        """Sync download (blocks). Prefer `download_data_async`."""
        try:
            return self._download_sync(object_name)
        except S3Error as e:
            logger.error("data_download_failed", object=object_name, error=str(e))
            raise

    # ---- Async wrappers (non-blocking) ----
    async def upload_data_async(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> str:
        try:
            return await asyncio.to_thread(self._upload_sync, object_name, data, content_type, metadata)
        except S3Error as e:
            logger.error("data_upload_failed", object=object_name, error=str(e))
            raise

    async def download_data_async(self, object_name: str) -> bytes:
        try:
            return await asyncio.to_thread(self._download_sync, object_name)
        except S3Error as e:
            logger.error("data_download_failed", object=object_name, error=str(e))
            raise

    async def object_exists_async(self, object_name: str) -> bool:
        def _exists():
            try:
                self.client.stat_object(self.bucket_name, object_name)
                return True
            except S3Error:
                return False

        return await asyncio.to_thread(_exists)

    async def get_presigned_url_async(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        def _url():
            return self.client.presigned_get_object(self.bucket_name, object_name, expires=expires)

        try:
            return await asyncio.to_thread(_url)
        except S3Error as e:
            logger.error("presigned_url_failed", object=object_name, error=str(e))
            raise

    # ---- Sync convenience still available ----
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

    def get_object_info(self, object_name: str) -> dict | None:
        """Sync get object info (stat) for verification. Returns dict with size, etag, content_type."""
        try:
            stat = self.client.stat_object(self.bucket_name, object_name)
            return {
                "size": stat.size,
                "etag": stat.etag,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "metadata": stat.metadata,
            }
        except S3Error as e:
            logger.warning("get_object_info_failed", object=object_name, error=str(e))
            return None
        except OSError as e:
            logger.warning("get_object_info_os_error", object=object_name, error=str(e))
            return None

    async def get_object_info_async(self, object_name: str) -> dict | None:
        """Async wrapper for get_object_info."""
        return await asyncio.to_thread(self.get_object_info, object_name)
