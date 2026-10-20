
from contextlib import contextmanager
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.postgres_connection import PostgreSQLConnectionError
from app.models.datasource import DataSource
from test_datasource_credentials import (
    auth,
    create_source,
    credential_payload,
    credential_url,
)
from test_datasources import (
    create_organization,
    datasource_url,
    register_and_login,
    test_client,
)


@pytest.fixture(autouse=True)
def isolated_connection_test(monkeypatch):
    # Never use the application's real encryption key.
    monkeypatch.setenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )

    # Prevent real DNS requests when configuring credentials.
    monkeypatch.setattr(
        "app.api.datasources.validate_database_host",
        lambda host: host,
    )

    # Prevent accidental real database connections.
    @contextmanager
    def blocked_connection(**kwargs):
        raise AssertionError("Unexpected real database connection")
        yield

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        blocked_connection,
    )


def connection_url(org_id, source_id):
    return f"{datasource_url(org_id)}/{source_id}/test-connection"


def configured_source(client, token):
    org_id = create_organization(client, token)
    source_id = create_source(client, org_id, token)

    response = client.put(
        credential_url(org_id, source_id),
        headers=auth(token),
        json=credential_payload(),
    )
    assert response.status_code == 200

    return org_id, source_id


def test_owner_can_verify_connection(test_client, monkeypatch):
    client, TestSession = test_client
    _, token = register_and_login(client)
    org_id, source_id = configured_source(client, token)

    calls = []

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query):
            assert query == "SELECT 1"

        def fetchone(self):
            return (1,)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    @contextmanager
    def fake_connection(**kwargs):
        calls.append(kwargs)
        yield FakeConnection()

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        fake_connection,
    )

    response = client.post(
        connection_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["data_source_id"] == source_id
    assert len(calls) == 1
    assert calls[0]["password"] == credential_payload()["password"]

    with TestSession() as session:
        source = session.get(DataSource, uuid.UUID(source_id))
        assert source.status == "connected"


def test_connection_failure_is_safe(test_client, monkeypatch):
    client, TestSession = test_client
    _, token = register_and_login(client)
    org_id, source_id = configured_source(client, token)

    @contextmanager
    def failed_connection(**kwargs):
        raise PostgreSQLConnectionError("Internal sensitive details")
        yield

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        failed_connection,
    )

    response = client.post(
        connection_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 502
    assert "Internal sensitive details" not in response.text
    assert "TestPassword123!" not in response.text

    with TestSession() as session:
        source = session.get(DataSource, uuid.UUID(source_id))
        assert source.status == "connection_failed"


def test_missing_credentials_rejected(test_client):
    client, _ = test_client
    _, token = register_and_login(client)
    org_id = create_organization(client, token)
    source_id = create_source(client, org_id, token)

    response = client.post(
        connection_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 400


def test_admin_can_test_connection(test_client, monkeypatch):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    admin_id, admin_token = register_and_login(client)

    org_id, source_id = configured_source(client, owner_token)

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth(owner_token),
        json={"user_id": admin_id, "role": "admin"},
    )
    assert added.status_code == 201

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query):
            assert query == "SELECT 1"

        def fetchone(self):
            return (1,)

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

    @contextmanager
    def fake_connection(**kwargs):
        yield FakeConnection()

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        fake_connection,
    )

    response = client.post(
        connection_url(org_id, source_id),
        headers=auth(admin_token),
    )

    assert response.status_code == 200


@pytest.mark.parametrize("role", ["viewer", "member"])
def test_read_only_roles_cannot_test_connection(test_client, role):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    user_id, user_token = register_and_login(client)
    org_id, source_id = configured_source(client, owner_token)

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth(owner_token),
        json={"user_id": user_id, "role": role},
    )
    assert added.status_code == 201

    response = client.post(
        connection_url(org_id, source_id),
        headers=auth(user_token),
    )

    assert response.status_code == 403


def test_cross_tenant_connection_denied(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(client, token_a)
    org_b, source_b = configured_source(client, token_b)

    response = client.post(
        connection_url(org_b, source_b),
        headers=auth(token_a),
    )
    assert response.status_code == 404

    response = client.post(
        connection_url(org_a, source_b),
        headers=auth(token_a),
    )
    assert response.status_code == 404


def test_connection_requires_authentication(test_client):
    client, _ = test_client

    response = client.post(
        connection_url(uuid.uuid4(), uuid.uuid4()),
    )

    assert response.status_code == 401


def test_unexpected_error_does_not_leak_secrets(
    test_client, monkeypatch
):
    client, _ = test_client
    _, token = register_and_login(client)
    org_id, source_id = configured_source(client, token)

    @contextmanager
    def broken_connection(**kwargs):
        raise RuntimeError("Sensitive server information")
        yield

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        broken_connection,
    )

    response = client.post(
        connection_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 500
    assert "Sensitive server information" not in response.text
    assert "TestPassword123!" not in response.text
