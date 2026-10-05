from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class SpecPayload(BaseModel):
    """Base simulation specification payload"""

    domain: str
    metadata: Dict[str, Any] = {}
    entities: List[Dict[str, Any]] = []
    navigation: Dict[str, Any] = {}
    lighting: Dict[str, Any] = {}
    copilot_policy: Dict[str, Any] = {}
    performance_budget: Dict[str, Any] = {}


class SpecCreate(BaseModel):
    payload_json: SpecPayload


class SpecUpdate(BaseModel):
    payload_json: Optional[SpecPayload] = None
    status: Optional[str] = None


class SpecResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    version: int
    payload_json: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class SpecGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    run_id: Optional[str] = Field(default=None, max_length=64)
    clarification_answers: Dict[str, Any] = Field(default_factory=dict)


class SpecClarifyRequest(BaseModel):
    answers: Dict[str, str] = Field(max_length=100)
    run_id: Optional[str] = Field(default=None, max_length=64)
    current_intake: Dict[str, Any] = Field(default_factory=dict)


class SpecValidateResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []


class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    run_id: Optional[str] = None


class GenerationRunResponse(BaseModel):
    id: str
    project_id: int
    stage: str
    status: str
    progress: int
    intake: Optional[Dict[str, Any]] = None
    clarification: Dict[str, Any] = {}
    error: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ScenePackageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    spec_id: int
    storage_key: str
    status: str
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ClarifyWithStateRequest(BaseModel):
    answers: Dict[str, str]
    current_intake: Dict[str, Any] = {}
    run_id: Optional[str] = None
