
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.jwt import create_access_token, verify_access_token
from app.core.security import verify_password
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def test_client():
    test_url = dotenv_values(
        Path(__file__).resolve().parents[1] / ".env.test"
    ).get("DATABASE_URL")

    if not test_url:
        pytest.fail("DATABASE_URL missing from backend/.env.test")

    parsed_url = make_url(test_url)

    if parsed_url.database != "insightflow_test":
        pytest.fail("Refusing to use a non-test database")

    engine = create_engine(test_url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            TestSession = sessionmaker(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )

            def override_get_db():
                with TestSession() as session:
                    yield session

            app.dependency_overrides[get_db] = override_get_db

            try:
                with TestClient(app) as client:
                    yield client, TestSession
            finally:
                app.dependency_overrides.pop(get_db, None)
                transaction.rollback()
    finally:
        engine.dispose()


def test_register_user_success(test_client):
    client, TestSession = test_client

    email = f"test-{uuid.uuid4().hex}@example.com"
    password = "SecureTestPassword123!"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Test User",
            "password": password,
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["email"] == email
    assert data["full_name"] == "Test User"
    assert "id" in data

    assert "password" not in data
    assert "hashed_password" not in data

    with TestSession() as session:
        user = session.scalar(
            select(User).where(User.email == email)
        )

        assert user is not None
        assert user.hashed_password != password
        assert verify_password(password, user.hashed_password)


def test_duplicate_email_rejected(test_client):
    client, _ = test_client

    email = f"duplicate-{uuid.uuid4().hex}@example.com"

    payload = {
        "email": email,
        "full_name": "Duplicate Test",
        "password": "SecureTestPassword123!",
    }

    first_response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert second_response.status_code == 409


def test_short_password_rejected(test_client):
    client, _ = test_client

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"short-{uuid.uuid4().hex}@example.com",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_invalid_email_rejected(test_client):
    client, _ = test_client

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "SecureTestPassword123!",
        },
    )

    assert response.status_code == 422


def test_login_success(test_client):
    client, _ = test_client

    email = f"login-{uuid.uuid4().hex}@example.com"
    password = "SecureTestPassword123!"

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Login Test",
            "password": password,
        },
    )

    assert registration.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)

    assert verify_access_token(
        data["access_token"]
    ) == uuid.UUID(registration.json()["id"])


def test_login_wrong_password(test_client):
    client, _ = test_client

    email = f"wrong-{uuid.uuid4().hex}@example.com"

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "CorrectPassword123!",
        },
    )

    assert registration.status_code == 201

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_login_unknown_user(test_client):
    client, _ = test_client

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": f"unknown-{uuid.uuid4().hex}@example.com",
            "password": "SecureTestPassword123!",
        },
    )

    assert response.status_code == 401


def test_login_invalid_email(test_client):
    client, _ = test_client

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "invalid-email",
            "password": "SecureTestPassword123!",
        },
    )

    assert response.status_code == 422


def test_me_with_valid_token(test_client):
    client, _ = test_client

    email = f"profile-{uuid.uuid4().hex}@example.com"
    password = "SecureTestPassword123!"

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Profile Test",
            "password": password,
        },
    )

    assert registration.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )

    assert login.status_code == 200

    token = login.json()["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == registration.json()["id"]
    assert response.json()["email"] == email
    assert "hashed_password" not in response.json()


def test_me_without_token(test_client):
    client, _ = test_client

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_with_invalid_token(test_client):
    client, _ = test_client

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_me_with_nonexistent_user(test_client):
    client, _ = test_client

    token = create_access_token(uuid.uuid4())

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
