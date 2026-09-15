"""Tests for API endpoints"""
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import get_settings
from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "name" in response.json()


@pytest.mark.asyncio
async def test_register_user(client):
    response = await client.post(
        "/v1/auth/register",
        json={"email": "register@example.com", "password": "testpass123", "name": "Test User"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "register@example.com"
    assert data["name"] == "Test User"
    assert "id" in data


@pytest.mark.asyncio
async def test_login_user(client):
    await client.post(
        "/v1/auth/register",
        json={"email": "login@example.com", "password": "testpass123", "name": "Login User"},
    )
    response = await client.post(
        "/v1/auth/login",
        data={"username": "login@example.com", "password": "testpass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_create_project(client, auth_headers):
    response = await client.post(
        "/v1/projects",
        json={"name": "My Test Project", "domain": "real_estate", "category": "apartment"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Test Project"
    assert data["domain"] == "real_estate"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_projects(client, auth_headers, test_project):
    response = await client.get("/v1/projects", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_get_project(client, auth_headers, test_project):
    response = await client.get(f"/v1/projects/{test_project.id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_project.id
    assert data["name"] == test_project.name


@pytest.mark.asyncio
async def test_update_project(client, auth_headers, test_project):
    response = await client.patch(
        f"/v1/projects/{test_project.id}",
        json={"name": "Updated Project Name"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Project Name"


@pytest.mark.asyncio
async def test_intake_prompt(client, auth_headers, test_project):
    response = await client.post(
        f"/v1/projects/{test_project.id}/intake",
        json={"prompt": "Create a modern 3-bedroom apartment"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "detected_domain" in data
    assert "suggested_questions" in data
    assert data["run_id"].startswith("run_")

    status_response = await client.get(
        f"/v1/projects/{test_project.id}/generation-runs/{data['run_id']}",
        headers=auth_headers,
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "needs_clarification"


@pytest.mark.asyncio
async def test_intake_retry_same_prompt_returns_existing_run(client, auth_headers, test_project):
    # Retry-after-timeout resubmits the same prompt+context. The unique
    # (project_id, input_hash) constraint must not surface a 500: the
    # existing run is returned instead (mirrors generate-spec dedupe).
    payload = {"prompt": "Create a modern 3-bedroom apartment"}
    first = await client.post(
        f"/v1/projects/{test_project.id}/intake",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 200
    second = await client.post(
        f"/v1/projects/{test_project.id}/intake",
        json=payload,
        headers=auth_headers,
    )
    assert second.status_code == 200
    data = second.json()
    assert data["run_id"] == first.json()["run_id"]
    assert data["deduped"] is True


@pytest.mark.asyncio
async def test_clarify_requirements(client, auth_headers, test_project):
    intake = await client.post(
        f"/v1/projects/{test_project.id}/intake",
        json={"prompt": "Create a modern 3-bedroom apartment"},
        headers=auth_headers,
    )
    run_id = intake.json()["run_id"]
    response = await client.post(
        f"/v1/projects/{test_project.id}/clarify",
        json={"answers": {"style": "modern", "bedrooms": "3"}, "run_id": run_id},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "updated_fields" in data
    assert data["run_id"] == run_id


@pytest.mark.asyncio
async def test_generate_spec(client, auth_headers, test_project):
    response = await client.post(
        f"/v1/projects/{test_project.id}/generate-spec",
        json={"prompt": "Create a modern 3-bedroom apartment"},
        headers=auth_headers,
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data


@pytest.mark.asyncio
async def test_invalid_token(client):
    response = await client.get(
        "/v1/projects",
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_unauthorized_access(client, auth_headers, test_project):
    response = await client.post(
        "/v1/auth/register",
        json={"email": "other@example.com", "password": "pass123", "name": "Other User"},
    )
    assert response.status_code == 201

    login_response = await client.post(
        "/v1/auth/login",
        data={"username": "other@example.com", "password": "pass123"},
    )
    other_token = login_response.json()["access_token"]

    response = await client.get(
        f"/v1/projects/{test_project.id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    # Cross-organization resources are intentionally hidden to avoid leaking IDs.
    assert response.status_code == 404
