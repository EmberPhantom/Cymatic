"""Tests for API endpoints"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from cymatic_shared.db import Base
from app.db.session import get_db
from app.core.config import get_settings
from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus
from app.models.simulation_spec import SimulationSpec, SpecStatus
from app.core.security import get_password_hash, create_access_token

settings = get_settings()

TEST_DATABASE_URL = "postgresql+asyncpg://cymatic:cymatic@localhost:5432/cymatic_test"

engine = create_async_engine(TEST_DATABASE_URL, echo=True)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(setup_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session(setup_db):
    async with TestingSessionLocal() as session:
        yield session


@pytest.fixture
async def test_user(db_session):
    user = User(
        email="test@example.com",
        name="Test User",
        hashed_password=get_password_hash("testpass123"),
        role=UserRole.CREATOR,
        organization_id=1,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def auth_headers(test_user):
    access_token = create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email, "org_id": test_user.organization_id}
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
async def test_project(db_session, test_user):
    project = Project(
        name="Test Project",
        domain="real_estate",
        category="apartment",
        organization_id=test_user.organization_id,
        created_by=test_user.id,
        status=ProjectStatus.DRAFT,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


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
        json={"email": "test@example.com", "password": "testpass123", "name": "Test User"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
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


@pytest.mark.asyncio
async def test_clarify_requirements(client, auth_headers, test_project):
    response = await client.post(
        f"/v1/projects/{test_project.id}/clarify",
        json={"answers": {"style": "modern", "bedrooms": "3"}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "updated_fields" in data


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
    assert response.status_code == 403
