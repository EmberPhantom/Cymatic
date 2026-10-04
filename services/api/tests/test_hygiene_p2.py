"""P2 API hygiene: orphan upload sweep, bounded project-asset list, global
stale-session sweep."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.asset import Asset, AssetStatus, AssetType
from app.models.project import ProjectStatus
from app.models.stream_session import StreamSession, StreamSessionStatus
from app.models.user import User, UserRole
from app.services.asset_maintenance import sweep_stale_uploading_assets


def _asset(org_id, project_id, key, status, created_at):
    return Asset(
        organization_id=org_id,
        project_id=project_id,
        filename=key.split("/")[-1],
        type=AssetType.IMAGE,
        storage_key=key,
        status=status,
        metadata_json={},
        created_at=created_at,
    )


class _FakeMinIO:
    def __init__(self, fail_keys=()):
        self.deleted = []
        self.fail_keys = set(fail_keys)

    def delete_object(self, key):
        self.deleted.append(key)
        if key in self.fail_keys:
            raise RuntimeError("minio down")
        return True


def _patch_minio(monkeypatch, fake):
    monkeypatch.setattr("app.services.asset_maintenance.get_minio_client", lambda: fake)


@pytest.mark.asyncio
async def test_sweep_deletes_aged_uploading_keeps_fresh(
    db_session, test_user, test_project, monkeypatch
):
    now = datetime.now(timezone.utc)
    fake = _FakeMinIO()
    _patch_minio(monkeypatch, fake)
    aged = _asset(
        test_user.organization_id,
        test_project.id,
        "orgs/1/aged.png",
        AssetStatus.UPLOADING,
        now - timedelta(hours=25),
    )
    fresh = _asset(
        test_user.organization_id,
        test_project.id,
        "orgs/1/fresh.png",
        AssetStatus.UPLOADING,
        now - timedelta(minutes=5),
    )
    ready_old = _asset(
        test_user.organization_id,
        test_project.id,
        "orgs/1/ready.png",
        AssetStatus.READY,
        now - timedelta(hours=50),
    )
    db_session.add_all([aged, fresh, ready_old])
    await db_session.commit()

    swept = await sweep_stale_uploading_assets(
        db_session, older_than_hours=24, limit=100
    )
    assert swept == 1
    assert fake.deleted == ["orgs/1/aged.png"]

    remaining = (await db_session.execute(select(Asset.storage_key))).scalars().all()
    assert "orgs/1/aged.png" not in remaining
    assert "orgs/1/fresh.png" in remaining
    assert "orgs/1/ready.png" in remaining


@pytest.mark.asyncio
async def test_sweep_storage_failure_still_deletes_row(
    db_session, test_user, test_project, monkeypatch
):
    now = datetime.now(timezone.utc)
    fake = _FakeMinIO(fail_keys={"orgs/1/broken.png"})
    _patch_minio(monkeypatch, fake)
    row = _asset(
        test_user.organization_id,
        test_project.id,
        "orgs/1/broken.png",
        AssetStatus.UPLOADING,
        now - timedelta(hours=30),
    )
    db_session.add(row)
    await db_session.commit()
    row_id = row.id

    swept = await sweep_stale_uploading_assets(
        db_session, older_than_hours=24, limit=100
    )
    assert swept == 1
    assert await db_session.scalar(select(Asset).where(Asset.id == row_id)) is None


@pytest.mark.asyncio
async def test_sweep_endpoint_admin_only(
    client,
    db_session,
    auth_headers,
    admin_auth_headers,
    test_user,
    test_project,
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    fake = _FakeMinIO()
    _patch_minio(monkeypatch, fake)
    db_session.add(
        _asset(
            test_user.organization_id,
            test_project.id,
            "orgs/1/endpoint-aged.png",
            AssetStatus.UPLOADING,
            now - timedelta(hours=30),
        )
    )
    await db_session.commit()

    denied = await client.post(
        "/v1/assets/maintenance/sweep-uploads", headers=auth_headers
    )
    assert denied.status_code == 403

    resp = await client.post(
        "/v1/assets/maintenance/sweep-uploads", headers=admin_auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["swept"] >= 1


@pytest.mark.asyncio
async def test_list_project_assets_pagination(
    client, db_session, auth_headers, test_user, test_project
):
    now = datetime.now(timezone.utc)
    for i in range(5):
        db_session.add(
            _asset(
                test_user.organization_id,
                test_project.id,
                f"orgs/1/paged-{i}.png",
                AssetStatus.READY,
                now - timedelta(minutes=i),
            )
        )
    await db_session.commit()

    base = f"/v1/assets/projects/{test_project.id}"
    full = await client.get(base, headers=auth_headers)
    assert full.status_code == 200
    assert len(full.json()) >= 5

    page = await client.get(f"{base}?skip=1&limit=2", headers=auth_headers)
    assert page.status_code == 200
    assert len(page.json()) == 2

    bad = await client.get(f"{base}?skip=0&limit=101", headers=auth_headers)
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_heartbeat_sweeps_other_users_stale_sessions(
    client, db_session, auth_headers, test_user, test_project
):
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()

    other = User(
        email=f"stale-{uuid.uuid4().hex[:10]}@example.com",
        name="Stale Owner",
        hashed_password=get_password_hash("testpass12345"),
        role=UserRole.CREATOR,
        organization_id=test_user.organization_id,
        is_active=True,
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    now = datetime.now(timezone.utc)
    stale = StreamSession(
        project_id=test_project.id,
        user_id=other.id,
        status=StreamSessionStatus.PENDING,
        started_at=now - timedelta(hours=2),
        created_at=now - timedelta(hours=2),
        last_heartbeat_at=None,
    )
    fresh = StreamSession(
        project_id=test_project.id,
        user_id=other.id,
        status=StreamSessionStatus.PENDING,
        started_at=now,
        created_at=now,
        last_heartbeat_at=None,
    )
    db_session.add_all([stale, fresh])
    await db_session.commit()
    stale_id, fresh_id = stale.id, fresh.id

    mine = await client.post(
        "/v1/render/sessions",
        json={
            "project_id": test_project.id,
            "device_id": "hb-dev",
            "app_version": "0.1.0",
        },
        headers=auth_headers,
    )
    assert mine.status_code == 201
    hb = await client.post(
        f"/v1/render/sessions/{mine.json()['id']}/heartbeat", headers=auth_headers
    )
    assert hb.status_code == 200
    assert hb.json()["swept_global"] >= 1

    db_session.expire_all()
    assert (
        await db_session.scalar(
            select(StreamSession.status).where(StreamSession.id == stale_id)
        )
    ) == StreamSessionStatus.DISCONNECTED
    assert (
        await db_session.scalar(
            select(StreamSession.status).where(StreamSession.id == fresh_id)
        )
    ) == StreamSessionStatus.PENDING


@pytest.mark.asyncio
async def test_single_stream_still_enforced(
    client, auth_headers, db_session, test_project
):
    """Global sweep must not relax the one-active-session-per-user rule."""
    test_project.status = ProjectStatus.PUBLISHED
    await db_session.commit()
    r1 = await client.post(
        "/v1/render/sessions",
        json={
            "project_id": test_project.id,
            "device_id": "single-1",
            "app_version": "0.1.0",
        },
        headers=auth_headers,
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/v1/render/sessions",
        json={
            "project_id": test_project.id,
            "device_id": "single-2",
            "app_version": "0.1.0",
        },
        headers=auth_headers,
    )
    assert r2.status_code == 409
