"""Planning sheet endpoints: build draft -> approve gates generation input."""

import pytest


@pytest.mark.asyncio
async def test_plan_build_approve_flow(
    client, auth_headers, admin_auth_headers, test_project
):
    # Intake (deterministic stub) creates the run the sheet is built from.
    intake = await client.post(
        f"/v1/projects/{test_project.id}/intake",
        json={"prompt": "Taj Mahal walkthrough"},
        headers=auth_headers,
    )
    assert intake.status_code == 200
    run_id = intake.json()["run_id"]

    build = await client.post(
        f"/v1/projects/{test_project.id}/plan",
        json={"run_id": run_id},
        headers=auth_headers,
    )
    assert build.status_code == 200
    body = build.json()
    assert body["status"] == "draft"
    assert body["version"] == 1
    assert body["run_id"] == run_id
    assert body["sheet"]["objective"] == "Taj Mahal walkthrough"

    latest = await client.get(
        f"/v1/projects/{test_project.id}/plan", headers=auth_headers
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == body["id"]

    approve = await client.post(
        f"/v1/projects/{test_project.id}/plan/{body['id']}/approve",
        headers=admin_auth_headers,
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # Second draft + approval supersedes the first.
    build2 = await client.post(
        f"/v1/projects/{test_project.id}/plan",
        json={"run_id": run_id},
        headers=auth_headers,
    )
    assert build2.json()["version"] == 2
    approve2 = await client.post(
        f"/v1/projects/{test_project.id}/plan/{build2.json()['id']}/approve",
        headers=admin_auth_headers,
    )
    assert approve2.json()["status"] == "approved"
    first = await client.get(
        f"/v1/projects/{test_project.id}/plan", headers=auth_headers
    )
    assert first.json()["id"] == build2.json()["id"]


@pytest.mark.asyncio
async def test_plan_unknown_run_404(client, auth_headers, test_project):
    resp = await client.post(
        f"/v1/projects/{test_project.id}/plan",
        json={"run_id": "run_does_not_exist"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_plan_none_404(client, auth_headers, test_project):
    resp = await client.get(
        f"/v1/projects/{test_project.id}/plan", headers=auth_headers
    )
    assert resp.status_code == 404
