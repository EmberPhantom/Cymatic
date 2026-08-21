"""MinIO / S3-compatible object storage client with connection pooling"""
import os
import io
from datetime import timedelta
from typing import Optional, BinaryIO, List
from minio import Minio
from minio.error import S3Error
from app.core.config import get_settings
import structlog
from urllib3 import PoolManager
from threading import Lock

logger = structlog.get_logger()
settings = get_settings()


class MinIOClient:
    """Wrapper for MinIO client with CYMATIC-specific methods and connection pooling."""
    
    # Class-level connection pool for reuse across instances
    _pool_manager: Optional[PoolManager] = None
    _pool_lock = Lock()
    
    def __init__(self, pool_size: int = 10, max_retries: int = 3):
        # Create connection pool if not exists
        with self._pool_lock:
            if MinIOClient._pool_manager is None:
                MinIOClient._pool_manager = PoolManager(
                    num_pools=pool_size,
                    maxsize=pool_size,
                    retries=max_retries,
                    timeout=30.0,
                )
        
        self.client = Minio(
            settings.S3_ENDPOINT.replace("http://", "").replace("https://", ""),
            access_key=settings.S3_ACCESS_KEY,
            secret_key=settings.S3_SECRET_KEY,
            secure=settings.S3_ENDPOINT.startswith("https"),
            region=settings.S3_REGION,
            http_client=MinIOClient._pool_manager,
        )
        self.bucket_name = settings.S3_BUCKET_NAME
        self._ensure_bucket()
    
    @classmethod
    def close_pool(cls):
        """Close the connection pool (call on shutdown)."""
        with cls._pool_lock:
            if cls._pool_manager:
                cls._pool_manager.clear()
                cls._pool_manager = None
    
    def _ensure_bucket(self):
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name, location=settings.S3_REGION)
                logger.info("bucket_created", bucket=self.bucket_name)
        except S3Error as e:
            logger.error("bucket_creation_failed", bucket=self.bucket_name, error=str(e))
            raise
    
    def upload_file(
        self,
        object_name: str,
        file_path: str,
        content_type: str = None,
        metadata: dict = None,
    ) -> str:
        """Upload a file from local path."""
        try:
            self.client.fput_object(
                self.bucket_name,
                object_name,
                file_path,
                content_type=content_type,
                metadata=metadata or {},
            )
            logger.info("file_uploaded", object=object_name, bucket=self.bucket_name)
            return object_name
        except S3Error as e:
            logger.error("file_upload_failed", object=object_name, error=str(e))
            raise
    
    def upload_data(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict = None,
    ) -> str:
        """Upload raw bytes data."""
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
    
    def upload_stream(
        self,
        object_name: str,
        stream: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: dict = None,
    ) -> str:
        """Upload from a file-like stream."""
        try:
            self.client.put_object(
                self.bucket_name,
                object_name,
                stream,
                length=length,
                content_type=content_type,
                metadata=metadata or {},
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
    
    def download_data(self, object_name: str) -> bytes:
        """Download object as bytes."""
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
        method: str = "GET",
    ) -> str:
        """Generate presigned URL for object access."""
        try:
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=expires,
            )
            logger.info("presigned_url_generated", object=object_name, method=method)
            return url
        except S3Error as e:
            logger.error("presigned_url_failed", object=object_name, error=str(e))
            raise
    
    def get_presigned_put_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1),
    ) -> str:
        """Generate presigned URL for uploading."""
        try:
            url = self.client.presigned_put_object(
                self.bucket_name,
                object_name,
                expires=expires,
            )
            logger.info("presigned_put_url_generated", object=object_name)
            return url
        except S3Error as e:
            logger.error("presigned_put_url_failed", object=object_name, error=str(e))
            raise
    
    def delete_object(self, object_name: str) -> bool:
        """Delete an object."""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info("object_deleted", object=object_name)
            return True
        except S3Error as e:
            logger.error("object_delete_failed", object=object_name, error=str(e))
            return False
    
    def delete_objects(self, object_names: List[str]) -> int:
        """Delete multiple objects."""
        deleted = 0
        for name in object_names:
            if self.delete_object(name):
                deleted += 1
        return deleted
    
    def object_exists(self, object_name: str) -> bool:
        """Check if object exists."""
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False
    
    def get_object_info(self, object_name: str) -> dict:
        """Get object metadata."""
        try:
            stat = self.client.stat_object(self.bucket_name, object_name)
            return {
                "name": stat.object_name,
                "size": stat.size,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified,
                "etag": stat.etag,
                "metadata": stat.metadata,
            }
        except S3Error as e:
            logger.error("object_info_failed", object=object_name, error=str(e))
            raise
    
    def list_objects(
        self,
        prefix: str = "",
        recursive: bool = True,
    ) -> List[dict]:
        """List objects with optional prefix."""
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=recursive,
            )
            return [
                {
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag,
                }
                for obj in objects
            ]
        except S3Error as e:
            logger.error("list_objects_failed", prefix=prefix, error=str(e))
            raise
    
    def copy_object(
        self,
        source_object: str,
        dest_object: str,
        metadata: dict = None,
    ) -> str:
        """Copy object within bucket."""
        try:
            self.client.copy_object(
                self.bucket_name,
                dest_object,
                f"/{self.bucket_name}/{source_object}",
                metadata=metadata,
            )
            logger.info("object_copied", source=source_object, dest=dest_object)
            return dest_object
        except S3Error as e:
            logger.error("object_copy_failed", source=source_object, dest=dest_object, error=str(e))
            raise


# Global MinIO client instance (lazy-loaded)
_minio_client_instance: Optional["MinIOClient"] = None


def get_minio_client() -> MinIOClient:
    global _minio_client_instance
    if _minio_client_instance is None:
        _minio_client_instance = MinIOClient()
    return _minio_client_instance


# Helper functions for common operations
def get_asset_storage_key(organization_id: int, project_id: int | None, filename: str) -> str:
    """Generate standardized storage key for assets."""
    if project_id:
        return f"orgs/{organization_id}/projects/{project_id}/assets/{filename}"
    return f"orgs/{organization_id}/assets/{filename}"


def get_scene_package_key(organization_id: int, project_id: int, spec_id: int, version: int) -> str:
    """Generate storage key for scene packages."""
    return f"orgs/{organization_id}/projects/{project_id}/scenes/spec_{spec_id}_v{version}.cymatic"


def get_asset_presigned_upload_url(organization_id: int, project_id: int | None, filename: str, expires_hours: int = 1) -> tuple[str, str]:
    """Get presigned upload URL and storage key for an asset."""
    storage_key = get_asset_storage_key(organization_id, project_id, filename)
    url = get_minio_client().get_presigned_put_url(storage_key, expires=timedelta(hours=expires_hours))
    return url, storage_key


def get_asset_presigned_download_url(storage_key: str, expires_hours: int = 1) -> str:
    """Get presigned download URL for an asset."""
    return get_minio_client().get_presigned_url(storage_key, expires=timedelta(hours=expires_hours))