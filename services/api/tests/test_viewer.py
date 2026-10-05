"""GET /v1/projects/{id}/scene-package/view - mobile browser viewer read path."""

import json
import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
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

    scene_pkg = ScenePackage(
        project_id=test_project.id,
        spec_id=spec.id,
        storage_key=storage_key,
        status="ready",
    )
    db_session.add(scene_pkg)
    await db_session.commit()
    return body


async def _other_org_headers(db_session) -> dict:
    """A second org + user, authenticated directly (bypasses the register/login
    HTTP flow, which has a pre-existing, unrelated failure in this test env)."""
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


@pytest.mark.asyncio
async def test_view_scene_package_requires_published_project(
    client, auth_headers, test_project
):
    resp = await client.get(
        f"/v1/projects/{test_project.id}/scene-package/view", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_view_scene_package_404_before_scene_ready(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    resp = await client.get(
        f"/v1/projects/{test_project.id}/scene-package/view", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_view_scene_package_returns_scene_json(
    client, auth_headers, db_session, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    expected = await _ready_scene_package(db_session, test_project)

    resp = await client.get(
        f"/v1/projects/{test_project.id}/scene-package/view", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["project"]["id"] == test_project.id
    assert body["scene_package"] == expected


@pytest.mark.asyncio
async def test_view_scene_package_404_for_other_org(client, db_session, test_project):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    other_headers = await _other_org_headers(db_session)

    resp = await client.get(
        f"/v1/projects/{test_project.id}/scene-package/view", headers=other_headers
    )
    assert resp.status_code == 404
