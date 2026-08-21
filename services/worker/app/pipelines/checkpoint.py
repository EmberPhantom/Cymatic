"""Pipeline Checkpointing for Resume Capability"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import json
import os
import structlog

logger = structlog.get_logger()


class PipelineCheckpoint(BaseModel):
    """Checkpoint data for pipeline resume capability."""
    project_id: int
    stage: str
    stage_index: int
    input_data: Dict[str, Any]
    stage_outputs: Dict[str, Any]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PipelineCheckpointManager:
    """Manages pipeline checkpoints for resume capability."""
    
    def __init__(self, checkpoint_dir: str = "/tmp/cymatic_checkpoints"):
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(self.checkpoint_dir, exist_ok=True)
    
    def _get_checkpoint_path(self, project_id: int) -> str:
        return os.path.join(self.checkpoint_dir, f"checkpoint_{project_id}.json")
    
    def save_checkpoint(self, checkpoint: 'PipelineCheckpoint'):
        """Save checkpoint to disk."""
        path = self._get_checkpoint_path(checkpoint.project_id)
        checkpoint.updated_at = datetime.utcnow()
        with open(path, 'w') as f:
            json.dump(checkpoint.model_dump(), f, default=str)
        logger.info("checkpoint_saved", project_id=checkpoint.project_id, stage=checkpoint.stage)
    
    def load_checkpoint(self, project_id: int) -> Optional['PipelineCheckpoint']:
        """Load checkpoint from disk."""
        path = self._get_checkpoint_path(project_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return PipelineCheckpoint(**data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("checkpoint_load_failed", project_id=project_id, error=str(e))
            return None
    
    def clear_checkpoint(self, project_id: int):
        """Clear checkpoint after successful completion."""
        path = self._get_checkpoint_path(project_id)
        if os.path.exists(path):
            os.remove(path)
            logger.info("checkpoint_cleared", project_id=project_id)


# Global checkpoint manager
checkpoint_manager = PipelineCheckpointManager()