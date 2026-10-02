"""POST /v1/render/* - native mobile render sessions (Unity-free path)."""

import json
import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.mobile_device import MobileDevice
from app.models.organization import Organization
from app.models.project import ProjectStatus
from app.models.scene_package import ScenePackage
from app.models.simulation_spec import SimulationSpec, SpecStatus
from app.models.user import User, UserRole
from app.services.minio_client import get_minio_client


async def _ready_scene_package(db_session, test_project) -> dict:
    body = {
        "metadata": {
            "format": "cymatic_v1",
            "spec_version": 1,
            "generated_at": "2026-01-01T00:00:00+00:00",
        },
        "domain": "real_estate",
        "entities": [],
        "navigation": {"points": [], "paths": [], "default_start_point": "start"},
        "lighting": {
            "preset": "neutral",
            "time_of_day": "noon",
            "ambient_intensity": 0.5,
            "sun_direction": [0.5, -1, 0.3],
            "custom_lights": [],
        },
        "copilot_policy": {},
        "performance_budget": {},
        "asset_manifest": {},
    }
    spec = SimulationSpec(
        project_id=test_project.id,
        version=1,
        payload_json={},
        status=SpecStatus.VALID,
    )
    db_session.add(spec)
    await db_session.flush()

    storage_key = f"orgs/{test_project.organization_id}/projects/{test_project.id}/scenes/spec_{spec.id}_v1.cymatic"
    raw = json.dumps(body).encode("utf-8")
    get_minio_client().upload_data(storage_key, raw, content_type="application/json")

    db_session.add(
        ScenePackage(
            project_id=test_project.id,
            spec_id=spec.id,
            storage_key=storage_key,
            status="ready",
        )
    )
    await db_session.commit()
    return body


async def _other_org_headers(db_session) -> dict:
    organization = Organization(name="Other Org", plan="free")
    db_session.add(organization)
    await db_session.flush()
    user = User(
        email=f"other-{uuid.uuid4().hex[:10]}@example.com",
        name="Other User",
        hashed_password=get_password_hash("testpass12345"),
        role=UserRole.VIEWER,
        organization_id=organization.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "org_id": user.organization_id}
    )
    return {"Authorization": f"Bearer {access_token}"}


def _payload(project_id, device="dev-1", version="0.1.0"):
    return {"project_id": project_id, "device_id": device, "app_version": version}


@pytest.mark.asyncio
async def test_render_create_unauthenticated(client, test_project):
    resp = await client.post("/v1/render/sessions", json=_payload(test_project.id))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_render_create_unknown_project(client, auth_headers):
    resp = await client.post(
        "/v1/render/sessions", json=_payload(999999), headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_render_create_requires_published(client, auth_headers, test_project):
    assert test_project.status != ProjectStatus.PUBLISHED
    resp = await client.post(
        "/v1/render/sessions", json=_payload(test_project.id), headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_render_create_happy_with_scene_url(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    await _ready_scene_package(db_session, test_project)

    resp = await client.post(
        "/v1/render/sessions", json=_payload(test_project.id), headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["project_id"] == test_project.id
    assert body["status"] == "pending"
    assert body["device_id"] == "dev-1"
    assert body["scene_url"] and "http" in body["scene_url"]


@pytest.mark.asyncio
async def test_render_create_second_session_conflicts(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    # publish check happens after project lookup; first session ok
    r1 = await client.post(
        "/v1/render/sessions", json=_payload(test_project.id), headers=auth_headers
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/v1/render/sessions",
        json=_payload(test_project.id, device="dev-2"),
        headers=auth_headers,
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_render_create_old_app_rejected(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    resp = await client.post(
        "/v1/render/sessions",
        json=_payload(test_project.id, version="0.0.1"),
        headers=auth_headers,
    )
    assert resp.status_code == 426


@pytest.mark.asyncio
async def test_render_create_revoked_device_forbidden(
    client, auth_headers, db_session, test_user, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    db_session.add(
        MobileDevice(user_id=test_user.id, device_id="lost-phone", revoked=True)
    )
    await db_session.commit()

    resp = await client.post(
        "/v1/render/sessions",
        json=_payload(test_project.id, device="lost-phone"),
        headers=auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stream_active_tolerates_render_session(
    client, auth_headers, db_session, test_project
):
    """Render sessions set started_at; stream readers must not 500 on them."""
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    r = await client.post(
        "/v1/render/sessions",
        json={"project_id": test_project.id, "device_id": "d1", "app_version": "0.1.0"},
        headers=auth_headers,
    )
    assert r.status_code == 201

    active = await client.get("/v1/stream/sessions/active", headers=auth_headers)
    assert active.status_code == 200
    assert active.json()["id"] == r.json()["id"]


@pytest.mark.asyncio
async def test_render_heartbeat_unknown_session(client, auth_headers):
    resp = await client.post(
        "/v1/render/sessions/999999/heartbeat", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_render_heartbeat_activates(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    r = await client.post(
        "/v1/render/sessions", json=_payload(test_project.id), headers=auth_headers
    )
    sid = r.json()["id"]

    hb = await client.post(f"/v1/render/sessions/{sid}/heartbeat", headers=auth_headers)
    assert hb.status_code == 200
    assert hb.json()["status"] == "active"


@pytest.mark.asyncio
async def test_render_end_closes_session(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    r = await client.post(
        "/v1/render/sessions", json=_payload(test_project.id), headers=auth_headers
    )
    sid = r.json()["id"]

    end = await client.post(f"/v1/render/sessions/{sid}/end", headers=auth_headers)
    assert end.status_code == 200
    assert end.json()["status"] == "disconnected"

    # After end, a new session is allowed again (no more active session).
    r2 = await client.post(
        "/v1/render/sessions",
        json=_payload(test_project.id, device="dev-2"),
        headers=auth_headers,
    )
    assert r2.status_code == 201


@pytest.mark.asyncio
async def test_render_voice_audio_unknown_session(client, auth_headers):
    resp = await client.post(
        "/v1/render/sessions/999999/voice/audio",
        files={"audio": ("ptt.wav", b"\x00" * 320, "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_render_voice_audio_empty_rejected(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    r = await client.post(
        "/v1/render/sessions", json=_payload(test_project.id), headers=auth_headers
    )
    sid = r.json()["id"]

    resp = await client.post(
        f"/v1/render/sessions/{sid}/voice/audio",
        files={"audio": ("empty.wav", b"", "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_render_cross_org_isolation(client, db_session, test_project):
    """Another org's user cannot start a render session on this project."""
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    other = await _other_org_headers(db_session)

    resp = await client.post(
        "/v1/render/sessions", json=_payload(test_project.id), headers=other
    )
    # Other user is VIEWER role -> require_creator denies with 403;
    # either way the project must not leak.
    assert resp.status_code in (403, 404)
