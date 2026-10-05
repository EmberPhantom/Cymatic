"""Render-core asset resolution: manifest URI -> downloadable bytes."""

import pytest

from app.models.asset import Asset, AssetStatus, AssetType


def _ready_asset(org_id, project_id, filename):
    return Asset(
        organization_id=org_id,
        project_id=project_id,
        filename=filename,
        type=AssetType.MODEL_3D,
        storage_key=f"orgs/{org_id}/projects/{project_id}/assets/{filename}",
        status=AssetStatus.READY,
        metadata_json={},
    )


@pytest.mark.asyncio
async def test_resolve_ready_asset_by_basename(
    client, auth_headers, db_session, test_user, test_project
):
    db_session.add(_ready_asset(test_user.organization_id, test_project.id, "room.glb"))
    await db_session.commit()
    resp = await client.get(
        "/v1/assets/resolve/url",
        params={"uri": "assets/models/room.glb", "project_id": test_project.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["download_url"].startswith("http")
    assert body["expires_hours"] == 1


@pytest.mark.asyncio
async def test_resolve_other_org_asset_404(
    client, db_session, test_user, test_project
):
    db_session.add(_ready_asset(test_user.organization_id, test_project.id, "villa.glb"))
    await db_session.commit()
    await client.post(
        "/v1/auth/register",
        json={"email": "reso@example.com", "password": "testpass12345", "name": "R"},
    )
    login = await client.post(
        "/v1/auth/login",
        data={"username": "reso@example.com", "password": "testpass12345"},
    )
    other = {"Authorization": f"Bearer {login.json()['access_token']}"}
    resp = await client.get(
        "/v1/assets/resolve/url", params={"uri": "assets/models/villa.glb"}, headers=other
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_template_catalog_procedural(client, auth_headers):
    resp = await client.get(
        "/v1/assets/resolve/url",
        params={"uri": "assets/models/living_modern.glb"},
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "template_not_baked"


@pytest.mark.asyncio
async def test_resolve_rejects_traversal_and_urls(client, auth_headers):
    for bad in ("../secret.glb", "http://evil/x.glb", "/etc/passwd"):
        resp = await client.get(
            "/v1/assets/resolve/url", params={"uri": bad}, headers=auth_headers
        )
        assert resp.status_code == 400, bad


@pytest.mark.asyncio
async def test_resolve_non_ready_is_not_found(
    client, auth_headers, db_session, test_user, test_project
):
    asset = _ready_asset(test_user.organization_id, test_project.id, "draft.glb")
    asset.status = AssetStatus.UPLOADED
    db_session.add(asset)
    await db_session.commit()
    resp = await client.get(
        "/v1/assets/resolve/url", params={"uri": "draft.glb"}, headers=auth_headers
    )
    assert resp.status_code == 404
