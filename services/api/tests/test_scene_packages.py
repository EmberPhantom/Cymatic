"""Scene-package helper failure semantics: None vs 503-unavailable."""

import pytest

from app.services.scene_packages import (
    ScenePackageUnavailable,
    get_latest_scene_package_json,
    get_latest_scene_package_url,
)


@pytest.mark.asyncio
async def test_helpers_none_when_no_package(db_session, test_project):
    assert await get_latest_scene_package_url(db_session, test_project.id) is None
    assert await get_latest_scene_package_json(db_session, test_project.id) is None


@pytest.mark.asyncio
async def test_helpers_raise_when_storage_down(db_session, test_project, monkeypatch):
    import app.services.scene_packages as helpers
    from app.models.scene_package import ScenePackage

    pkg = ScenePackage(
        project_id=test_project.id,
        spec_id=1,
        storage_key="orgs/1/projects/1/scenes/missing.cymatic",
        status="ready",
    )
    db_session.add(pkg)
    await db_session.commit()

    class Broken:
        def get_presigned_url(self, *a, **k):
            raise OSError("minio down")

        def download_data(self, *a, **k):
            raise OSError("minio down")

    monkeypatch.setattr(helpers, "get_minio_client", lambda: Broken())
    with pytest.raises(ScenePackageUnavailable):
        await helpers.get_latest_scene_package_url(db_session, test_project.id)
    with pytest.raises(ScenePackageUnavailable):
        await helpers.get_latest_scene_package_json(db_session, test_project.id)
