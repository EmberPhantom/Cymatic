"""Unit tests for audit middleware action/resource mapping (pure functions)."""
from app.core.middleware import AuditLoggingMiddleware


def _mw():
    return AuditLoggingMiddleware(app=None)  # type: ignore[arg-type]


def test_determine_action_generation_flow():
    mw = _mw()
    assert mw._determine_action("POST", "/v1/projects/1/generate-spec") == "spec_generated"
    assert mw._determine_action("POST", "/v1/projects/1/generate-scene") == "scene_generated"
    assert mw._determine_action("POST", "/v1/projects/2/publish") == "scene_published"
    assert mw._determine_action("POST", "/v1/projects") == "project_created"
    assert mw._determine_action("PATCH", "/v1/projects/1") == "project_updated"
    assert mw._determine_action("DELETE", "/v1/projects/1") == "project_deleted"
    assert mw._determine_action("POST", "/v1/stream/sessions") == "stream_session_started"
    assert mw._determine_action("GET", "/v1/projects/1") is None


def test_extract_resource_ids():
    mw = _mw()
    assert mw._extract_resource("/v1/projects/42") == ("project", 42)
    assert mw._extract_resource("/v1/assets/abc") == ("asset", None)
    assert mw._extract_resource("/health") == (None, None)
