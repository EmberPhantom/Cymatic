"""Shared MinIO client for object storage operations."""

import asyncio
import io
from datetime import timedelta
from threading import Lock
from typing import BinaryIO
from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error
from urllib3 import PoolManager
import structlog

logger = structlog.get_logger()


class MinIOClient:
    """MinIO client wrapper for uploads/downloads.

    Sync methods are retained for backward compat but delegate to threadpool
    when called from async context via `*_async` variants to avoid blocking the event loop.
    A class-level urllib3 pool is shared across instances (single source,
    promoted from the former api fork).
    """

    _pool_manager: PoolManager | None = None
    _pool_lock = Lock()

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        region: str = "us-east-1",
        pool_size: int = 10,
        max_retries: int = 3,
    ):
        with MinIOClient._pool_lock:
            if MinIOClient._pool_manager is None:
                MinIOClient._pool_manager = PoolManager(
                    num_pools=pool_size,
                    maxsize=pool_size,
                    retries=max_retries,
                    timeout=30.0,
                )
        self.client = Minio(
            endpoint.replace("http://", "").replace("https://", ""),
            access_key=access_key,
            secret_key=secret_key,
            secure=endpoint.startswith("https"),
            region=region,
            http_client=MinIOClient._pool_manager,
        )
        self.bucket_name = bucket_name
        self.region = region
        self._ensure_bucket()

    @classmethod
    def close_pool(cls):
        """Drop the shared pool (call on shutdown/tests)."""
        with cls._pool_lock:
            if cls._pool_manager:
                cls._pool_manager.clear()
                cls._pool_manager = None

    def _ensure_bucket(self):
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name, location=self.region)
                logger.info("bucket_created", bucket=self.bucket_name)
        except S3Error as e:
            logger.error(
                "bucket_creation_failed", bucket=self.bucket_name, error=str(e)
            )
        except OSError as e:
            logger.warning(
                "bucket_check_deferred", bucket=self.bucket_name, error=str(e)
            )

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
            return await asyncio.to_thread(
                self._upload_sync, object_name, data, content_type, metadata
            )
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
            return self.client.presigned_get_object(
                self.bucket_name, object_name, expires=expires
            )

        try:
            return await asyncio.to_thread(_url)
        except S3Error as e:
            logger.error("presigned_url_failed", object=object_name, error=str(e))
            raise

    def upload_file(
        self,
        object_name: str,
        file_path: str,
        content_type: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Upload a file from local path."""
        try:
            self.client.fput_object(
                self.bucket_name,
                object_name,
                file_path,
                content_type=content_type or "application/octet-stream",
                metadata=metadata,
            )
            logger.info("file_uploaded", object=object_name, bucket=self.bucket_name)
            return object_name
        except S3Error as e:
            logger.error("file_upload_failed", object=object_name, error=str(e))
            raise

    def upload_stream(
        self,
        object_name: str,
        stream: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: dict | None = None,
    ) -> str:
        """Upload from a file-like stream."""
        try:
            self.client.put_object(
                self.bucket_name,
                object_name,
                stream,
                length=length,
                content_type=content_type,
                metadata=metadata,
            )
            logger.info("stream_uploaded", object=object_name, size=length)
            return object_name
        except S3Error as e:
            logger.error("stream_upload_failed", object=object_name, error=str(e))
            raise

    def download_file(self, object_name: str, file_path: str) -> str:
        """Download object to local file."""
        try:
            self.client.fget_object(self.bucket_name, object_name, file_path)
            logger.info("file_downloaded", object=object_name, path=file_path)
            return file_path
        except S3Error as e:
            logger.error("file_download_failed", object=object_name, error=str(e))
            raise

    # ---- Sync convenience still available ----
    def get_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
        method: str = "GET",
    ) -> str:
        """Presigned URL, branched by method (PUT -> upload, else download)."""
        try:
            m = method.upper()
            if m == "PUT":
                url = self.client.presigned_put_object(
                    self.bucket_name, object_name, expires=expires
                )
            else:
                url = self.client.presigned_get_object(
                    self.bucket_name, object_name, expires=expires
                )
            logger.info("presigned_url_generated", object=object_name, method=m)
            return url
        except S3Error as e:
            logger.error("presigned_url_failed", object=object_name, error=str(e))
            raise

    def get_presigned_put_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Presigned URL for uploading."""
        try:
            url = self.client.presigned_put_object(
                self.bucket_name, object_name, expires=expires
            )
            logger.info("presigned_put_url_generated", object=object_name)
            return url
        except S3Error as e:
            logger.error("presigned_put_url_failed", object=object_name, error=str(e))
            raise

    def delete_object(self, object_name: str) -> bool:
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info("object_deleted", object=object_name)
            return True
        except S3Error as e:
            logger.error("object_delete_failed", object=object_name, error=str(e))
            return False

    def delete_objects(self, object_names: list[str]) -> int:
        return sum(1 for name in object_names if self.delete_object(name))

    def list_objects(self, prefix: str = "", recursive: bool = True) -> list[dict]:
        try:
            return [
                {
                    "name": o.object_name,
                    "size": o.size,
                    "last_modified": o.last_modified,
                    "etag": o.etag,
                }
                for o in self.client.list_objects(
                    self.bucket_name, prefix=prefix, recursive=recursive
                )
            ]
        except S3Error as e:
            logger.error("list_objects_failed", prefix=prefix, error=str(e))
            raise

    def copy_object(
        self, source_object: str, dest_object: str, metadata: dict | None = None
    ) -> str:
        try:
            self.client.copy_object(
                self.bucket_name,
                dest_object,
                CopySource(self.bucket_name, source_object),
                metadata=metadata,
            )
            logger.info("object_copied", source=source_object, dest=dest_object)
            return dest_object
        except S3Error as e:
            logger.error(
                "object_copy_failed",
                source=source_object,
                dest=dest_object,
                error=str(e),
            )
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
