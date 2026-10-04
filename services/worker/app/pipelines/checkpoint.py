"""Pipeline Checkpointing for Resume Capability

Checkpoint storage:
- Primary: filesystem at CHECKPOINT_DIR (default /data/cymatic_checkpoints, fallback /tmp/cymatic_checkpoints).
- /tmp is ephemeral; /data persists across container restarts via Docker volume. REDIS fallback could be added
  for multi-replica deployments but filesystem remains for MVP single-worker.
- Writes are atomic via temp file + rename to avoid torn checkpoints on crash.
- Per-run files: checkpoint_{project_id}_{run_id}.json isolates concurrent
  reruns of the same project. The legacy single-per-project file
  checkpoint_{project_id}.json is still written when no run_id is known and
  is used as a read fallback so old checkpoints keep resuming.
- TTL: checkpoints older than CHECKPOINT_TTL_HOURS (default 24) are treated
  as stale on load (ignored + pruned) so a days-old failure can never
  hijack a fresh run.
- Size guard: a single stage output larger than CHECKPOINT_MAX_STAGE_BYTES
  (default 1MB) is stored as a pointer/summary, never the full payload, so
  one giant architect dump cannot bloat or break checkpoint I/O.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
import json
import os
import tempfile
import structlog

logger = structlog.get_logger()

DEFAULT_CHECKPOINT_TTL_HOURS = 24.0
DEFAULT_CHECKPOINT_MAX_STAGE_BYTES = 1_000_000


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
    # Generation-run id that owns this checkpoint. None = legacy
    # single-per-project checkpoint (pre-run-id files still parse via the
    # Optional default and load via the legacy-name fallback).
    run_id: str | None = None
    stage: str
    stage_index: int
    input_data: Dict[str, Any]
    stage_outputs: Dict[str, Any]
    # Terminal status that stopped the pipeline ("in_progress" while running;
    # e.g. "validation_failed" after an early return). Resume logic keys off
    # this instead of misdiagnosing a failure checkpoint as a fresh start.
    # Optional with defaults so pre-existing checkpoint files still parse.
    status: str = "in_progress"
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _checkpoint_ttl_hours() -> float:
    """Stale-checkpoint TTL in hours (env CHECKPOINT_TTL_HOURS, default 24)."""
    try:
        return float(
            os.getenv("CHECKPOINT_TTL_HOURS", str(DEFAULT_CHECKPOINT_TTL_HOURS))
        )
    except (TypeError, ValueError):
        return DEFAULT_CHECKPOINT_TTL_HOURS


def _checkpoint_max_stage_bytes() -> int:
    """Per-stage serialized cap in bytes (env CHECKPOINT_MAX_STAGE_BYTES)."""
    try:
        return int(
            os.getenv(
                "CHECKPOINT_MAX_STAGE_BYTES", str(DEFAULT_CHECKPOINT_MAX_STAGE_BYTES)
            )
        )
    except (TypeError, ValueError):
        return DEFAULT_CHECKPOINT_MAX_STAGE_BYTES


def _parse_checkpoint_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        try:
            ts = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


class PipelineCheckpointManager:
    """Manages pipeline checkpoints for resume capability."""

    def __init__(
        self,
        checkpoint_dir: str | None = None,
        ttl_hours: float | None = None,
        max_stage_bytes: int | None = None,
    ):
        self.checkpoint_dir = checkpoint_dir or _resolve_checkpoint_dir()
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        self.ttl_hours = ttl_hours if ttl_hours is not None else _checkpoint_ttl_hours()
        self.max_stage_bytes = (
            max_stage_bytes
            if max_stage_bytes is not None
            else _checkpoint_max_stage_bytes()
        )

    def _get_checkpoint_path(self, project_id: int, run_id: str | None = None) -> str:
        if run_id:
            return os.path.join(
                self.checkpoint_dir, f"checkpoint_{project_id}_{run_id}.json"
            )
        return os.path.join(self.checkpoint_dir, f"checkpoint_{project_id}.json")

    def _guard_stage_outputs(self, stage_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Copy stage outputs, replacing oversize stages with a pointer.

        Returns a NEW dict; the caller's data is never mutated. Each stage
        value is measured serialized (the same bytes that hit disk); stages
        over the cap become {"_truncated": True, ...} with a text preview so
        resume still sees every stage key while disk stays bounded.
        """
        guarded: Dict[str, Any] = {}
        for stage, value in (stage_outputs or {}).items():
            try:
                raw = json.dumps(value, default=str)
            except (TypeError, ValueError):
                raw = ""
            size = len(raw.encode("utf-8"))
            if size > self.max_stage_bytes:
                guarded[stage] = {
                    "_truncated": True,
                    "stage": stage,
                    "bytes": size,
                    "summary": (
                        f"stage output ({size} bytes) exceeded "
                        f"CHECKPOINT_MAX_STAGE_BYTES={self.max_stage_bytes}; "
                        "full payload not checkpointed"
                    ),
                    "preview": raw[:500],
                }
                logger.warning(
                    "checkpoint_stage_truncated",
                    stage=stage,
                    bytes=size,
                    cap=self.max_stage_bytes,
                )
            else:
                guarded[stage] = value
        return guarded

    def _is_stale(self, updated_at: Any, mtime_fallback: float) -> bool:
        """True when the checkpoint is older than the TTL."""
        ts = _parse_checkpoint_time(updated_at)
        if ts is None:
            try:
                ts = datetime.fromtimestamp(mtime_fallback, tz=timezone.utc)
            except (OSError, OverflowError, ValueError):
                return False
        return (datetime.now(timezone.utc) - ts) > timedelta(hours=self.ttl_hours)

    def _prune(self, path: str, project_id: int, reason: str) -> None:
        try:
            os.remove(path)
            logger.info(
                "checkpoint_pruned", project_id=project_id, path=path, reason=reason
            )
        except OSError:
            pass

    def save_checkpoint(self, checkpoint: "PipelineCheckpoint"):
        """Save checkpoint to disk atomically.

        Per-run id isolates concurrent reruns (checkpoint_{project}_{run});
        without a run_id the legacy single-per-project file is written.
        Oversize stage outputs are stored as pointers (see size guard).
        """
        path = self._get_checkpoint_path(checkpoint.project_id, checkpoint.run_id)
        checkpoint.updated_at = datetime.now(timezone.utc)
        data = checkpoint.model_dump()
        data["stage_outputs"] = self._guard_stage_outputs(checkpoint.stage_outputs)
        # Atomic write: temp file in same dir + fsync + rename (HIGH: non-atomic write)
        dir_name = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(dir_name, exist_ok=True)
        tmp_prefix = (
            f".tmp_ckpt_{checkpoint.project_id}_{checkpoint.run_id or 'legacy'}_"
        )
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=tmp_prefix)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, default=str)
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
            run_id=checkpoint.run_id,
            stage=checkpoint.stage,
            dir=self.checkpoint_dir,
        )

    def load_checkpoint(
        self, project_id: int, run_id: str | None = None
    ) -> Optional["PipelineCheckpoint"]:
        """Load checkpoint from disk.

        With a run_id the per-run file wins; the legacy single-per-project
        file is the fallback (pre-run-id checkpoints keep resuming). Stale
        checkpoints (older than the TTL) are ignored AND pruned.
        """
        candidates = []
        if run_id:
            candidates.append(self._get_checkpoint_path(project_id, run_id))
        candidates.append(self._get_checkpoint_path(project_id))
        for path in candidates:
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                checkpoint = PipelineCheckpoint(**data)
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(
                    "checkpoint_load_failed", project_id=project_id, error=str(e)
                )
                return None
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = datetime.now(timezone.utc).timestamp()
            if self._is_stale(checkpoint.updated_at, mtime):
                self._prune(path, project_id, reason="stale_ttl")
                continue
            return checkpoint
        return None

    def clear_checkpoint(self, project_id: int, run_id: str | None = None):
        """Clear checkpoint after successful completion.

        With a run_id only the per-run file is removed (other concurrent runs
        of the same project are untouched); without one the legacy file is
        removed.
        """
        path = self._get_checkpoint_path(project_id, run_id)
        if os.path.exists(path):
            os.remove(path)
            logger.info("checkpoint_cleared", project_id=project_id, run_id=run_id)

    def prune_stale(self, limit: int = 1000) -> int:
        """Delete every checkpoint file in the dir older than the TTL.

        Best-effort maintenance sweep; returns the number of files removed.
        """
        pruned = 0
        try:
            names = os.listdir(self.checkpoint_dir)
        except OSError:
            return 0
        for name in names:
            if pruned >= limit:
                break
            if not (name.startswith("checkpoint_") and name.endswith(".json")):
                continue
            path = os.path.join(self.checkpoint_dir, name)
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                updated_at = data.get("updated_at")
                project_id = data.get("project_id", -1)
            except (OSError, json.JSONDecodeError, ValueError):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            if self._is_stale(updated_at, mtime):
                self._prune(path, project_id, reason="stale_ttl_sweep")
                pruned += 1
        return pruned


# Global checkpoint manager
checkpoint_manager = PipelineCheckpointManager()
