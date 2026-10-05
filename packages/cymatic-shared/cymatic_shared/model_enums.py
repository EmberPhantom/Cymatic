"""Shared lifecycle enums (ORM-free: safe to import from any service).

Placed here rather than beside the ORM models so api code — which keeps
its own model duplicates on the same MetaData — can use the enums without
triggering duplicate table registration.
"""

import enum


class RunStatus(str, enum.Enum):
    """Lifecycle states written to generation_runs.status (all producers)."""

    DRAFT = "draft"
    QUEUED = "queued"
    GENERATING_SPEC = "generating_spec"
    VALIDATING_SPEC = "validating_spec"
    NEEDS_CLARIFICATION = "needs_clarification"
    SPEC_READY = "spec_ready"
    READY_FOR_SPEC = "ready_for_spec"
    GENERATING_SCENE = "generating_scene"
    SCENE_READY = "scene_ready"
    FAILED = "failed"


class RunStage(str, enum.Enum):
    """Pipeline stages written to generation_runs.stage."""

    INTAKE = "intake"
    CLARIFICATION = "clarification"
    SPEC = "spec"
    VALIDATION = "validation"
    SCENE = "scene"
    ARTIFACT_VERIFICATION = "artifact_verification"


class RuntimeEventType(str, enum.Enum):
    """Well-known session event types (clients may send others; analytics keys on these)."""

    NAVIGATION_POINT_CHANGED = "navigation_point_changed"
    COPILOT_MESSAGE_SENT = "copilot_message_sent"
    VOICE_SESSION_STARTED = "voice_session_started"
    VOICE_SESSION_COMPLETED = "voice_session_completed"
    TOUR_COMPLETED = "tour_completed"
    SESSION_COMPLETED = "session_completed"
    WALKTHROUGH_COMPLETED = "walkthrough_completed"
