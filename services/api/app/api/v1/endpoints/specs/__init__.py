"""Simulation-spec endpoints (split package; routes unchanged)."""
from fastapi import APIRouter

from . import intake as _intake  # noqa: F401  (route registration)
from . import generate as _generate  # noqa: F401
from . import library as _library  # noqa: F401
from . import scene as _scene  # noqa: F401
from .schemas import (  # noqa: F401
    SpecPayload, SpecCreate, SpecUpdate, SpecResponse,
    SpecGenerateRequest, SpecClarifyRequest, SpecValidateResponse,
    JobResponse, GenerationRunResponse, ScenePackageResponse,
    ClarifyWithStateRequest,
)
# Agent entry points resolved through this namespace so tests can
# monkeypatch app.api.v1.endpoints.specs.process_* (see conftest).
from cymatic_shared.agents.intake_agent import process_intake  # noqa: F401
from cymatic_shared.agents.clarification_agent import (  # noqa: F401
    process_clarification_answers,
)

router = APIRouter()
router.include_router(_intake.router)
router.include_router(_generate.router)
router.include_router(_library.router)
router.include_router(_scene.router)
