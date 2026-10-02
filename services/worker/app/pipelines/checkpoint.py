"""Pipeline Checkpointing for Resume Capability

Checkpoint storage:
- Primary: filesystem at CHECKPOINT_DIR (default /data/cymatic_checkpoints, fallback /tmp/cymatic_checkpoints).
- /tmp is ephemeral; /data persists across container restarts via Docker volume. REDIS fallback could be added
  for multi-replica deployments but filesystem remains for MVP single-worker.
- Writes are atomic via temp file + rename to avoid torn checkpoints on crash.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import json
import os
import tempfile
import structlog

logger = structlog.get_logger()


def _resolve_checkpoint_dir() -> str:
    # Prefer explicit env, then persistent /data, then ephemeral /tmp
    env_dir = os.getenv("CHECKPOINT_DIR")
    if env_dir:
        return env_dir
    # Check if /data is writable/persistent (Docker volume)
    data_dir = "/data/cymatic_checkpoints"
    try:
        os.makedirs(data_dir, exist_ok=True)
        # Probe writability
        test_path = os.path.join(data_dir, ".probe")
        with open(test_path, "w") as f:
            f.write("probe")
        os.remove(test_path)
        return data_dir
    except OSError:
        return "/tmp/cymatic_checkpoints"


class PipelineCheckpoint(BaseModel):
    """Checkpoint data for pipeline resume capability."""

    project_id: int
    stage: str
    stage_index: int
    input_data: Dict[str, Any]
    stage_outputs: Dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineCheckpointManager:
    """Manages pipeline checkpoints for resume capability."""

    def __init__(self, checkpoint_dir: str | None = None):
        self.checkpoint_dir = checkpoint_dir or _resolve_checkpoint_dir()
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    def _get_checkpoint_path(self, project_id: int) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_{project_id}.json")

    def save_checkpoint(self, checkpoint: "PipelineCheckpoint"):
        """Save checkpoint to disk atomically."""
        path = self._get_checkpoint_path(checkpoint.project_id)
        checkpoint.updated_at = datetime.now(timezone.utc)
        # Atomic write: temp file in same dir + fsync + rename (HIGH: non-atomic write)
        dir_name = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(dir_name, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=dir_name, prefix=f".tmp_ckpt_{checkpoint.project_id}_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(checkpoint.model_dump(), f, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
        logger.info(
            "checkpoint_saved",
            project_id=checkpoint.project_id,
            stage=checkpoint.stage,
            dir=self.checkpoint_dir,
        )

    def load_checkpoint(self, project_id: int) -> Optional["PipelineCheckpoint"]:
        """Load checkpoint from disk."""
        path = self._get_checkpoint_path(project_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return PipelineCheckpoint(**data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                "checkpoint_load_failed", project_id=project_id, error=str(e)
            )
            return None

    def clear_checkpoint(self, project_id: int):
        """Clear checkpoint after successful completion."""
        path = self._get_checkpoint_path(project_id)
        if os.path.exists(path):
            os.remove(path)
            logger.info("checkpoint_cleared", project_id=project_id)


# Global checkpoint manager
checkpoint_manager = PipelineCheckpointManager()
