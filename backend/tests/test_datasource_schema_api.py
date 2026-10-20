
from contextlib import contextmanager
import uuid

import pytest

from test_datasource_connection_api import (
    auth,
    configured_source,
    create_organization,
    create_source,
    register_and_login,
    test_client,
)


# --------------------------------------------------
# TEST ISOLATION
# --------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_schema_api_test(monkeypatch):
    """
    Prevent real DNS requests during credential setup
    and use a temporary encryption key for each test.
    """
    from cryptography.fernet import Fernet

    monkeypatch.setenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )

    monkeypatch.setattr(
        "app.api.datasources.validate_database_host",
        lambda host: host,
    )


# --------------------------------------------------
# TEST HELPERS
# --------------------------------------------------

def schema_url(org_id, source_id):
    return (
        f"/api/v1/organizations/{org_id}"
        f"/data-sources/{source_id}/schema"
    )


SAMPLE_SCHEMA = {
    "table_count": 1,
    "tables": [
        {
            "schema": "public",
            "table": "customers",
            "columns": [
                {
                    "name": "id",
                    "data_type": "uuid",
                    "nullable": False,
                }
            ],
            "primary_keys": ["id"],
            "foreign_keys": [],
        }
    ],
}


def mock_schema_discovery(monkeypatch):
    """
    Mock the external PostgreSQL connection and
    return predictable schema discovery results.
    """
    calls = []

    @contextmanager
    def fake_connection(**kwargs):
        calls.append(kwargs)
        yield object()

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        fake_connection,
    )

    monkeypatch.setattr(
        "app.api.datasources.discover_postgres_schema",
        lambda connection: SAMPLE_SCHEMA,
    )

    return calls


# --------------------------------------------------
# OWNER CAN DISCOVER SCHEMA
# --------------------------------------------------

def test_owner_can_discover_schema(test_client, monkeypatch):
    client, _ = test_client

    _, token = register_and_login(client)

    org_id, source_id = configured_source(
        client,
        token,
    )

    calls = mock_schema_discovery(monkeypatch)

    response = client.get(
        schema_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 200

    result = response.json()

    # The API includes the data source identifier
    # alongside the discovered schema.
    assert result["data_source_id"] == str(source_id)
    assert result["table_count"] == SAMPLE_SCHEMA["table_count"]
    assert result["tables"] == SAMPLE_SCHEMA["tables"]

    # Exactly one mocked connection was opened.
    assert len(calls) == 1

    # The decrypted password reaches the connection adapter.
    assert calls[0]["password"] == "TestPassword123!"

    # The API response must never expose the password.
    assert "TestPassword123!" not in response.text


# --------------------------------------------------
# ORGANIZATION ROLES CAN DISCOVER SCHEMA
# --------------------------------------------------

@pytest.mark.parametrize(
    "role",
    ["admin", "member", "viewer"],
)
def test_organization_roles_can_discover_schema(
    test_client,
    monkeypatch,
    role,
):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    user_id, user_token = register_and_login(client)

    org_id, source_id = configured_source(
        client,
        owner_token,
    )

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth(owner_token),
        json={
            "user_id": user_id,
            "role": role,
        },
    )

    assert added.status_code == 201

    mock_schema_discovery(monkeypatch)

    response = client.get(
        schema_url(org_id, source_id),
        headers=auth(user_token),
    )

    assert response.status_code == 200

    result = response.json()

    assert result["data_source_id"] == str(source_id)
    assert result["table_count"] == 1


# --------------------------------------------------
# AUTHENTICATION REQUIRED
# --------------------------------------------------

def test_schema_requires_authentication(test_client):
    client, _ = test_client

    response = client.get(
        schema_url(
            uuid.uuid4(),
            uuid.uuid4(),
        )
    )

    assert response.status_code == 401


# --------------------------------------------------
# CROSS-TENANT ACCESS DENIED
# --------------------------------------------------

def test_cross_tenant_schema_access_denied(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(
        client,
        token_a,
    )

    org_b, source_b = configured_source(
        client,
        token_b,
    )

    # Organization A cannot access organization B.
    response = client.get(
        schema_url(org_b, source_b),
        headers=auth(token_a),
    )

    assert response.status_code == 404

    # Organization A cannot access a source
    # belonging to organization B.
    response = client.get(
        schema_url(org_a, source_b),
        headers=auth(token_a),
    )

    assert response.status_code == 404


# --------------------------------------------------
# MISSING CREDENTIALS REJECTED
# --------------------------------------------------

def test_missing_credentials_rejected(test_client):
    client, _ = test_client

    _, token = register_and_login(client)

    org_id = create_organization(
        client,
        token,
    )

    source_id = create_source(
        client,
        org_id,
        token,
    )

    response = client.get(
        schema_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 400


# --------------------------------------------------
# CONNECTION FAILURES ARE SANITIZED
# --------------------------------------------------

def test_connection_failure_is_sanitized(
    test_client,
    monkeypatch,
):
    from app.core.postgres_connection import (
        PostgreSQLConnectionError,
    )

    client, _ = test_client

    _, token = register_and_login(client)

    org_id, source_id = configured_source(
        client,
        token,
    )

    @contextmanager
    def failed_connection(**kwargs):
        raise PostgreSQLConnectionError(
            "Sensitive database server information"
        )
        yield

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        failed_connection,
    )

    response = client.get(
        schema_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 502

    # Internal connection details must not leak.
    assert (
        "Sensitive database server information"
        not in response.text
    )

    assert "TestPassword123!" not in response.text


# --------------------------------------------------
# SCHEMA DISCOVERY FAILURES ARE SANITIZED
# --------------------------------------------------

def test_schema_discovery_failure_is_sanitized(
    test_client,
    monkeypatch,
):
    from app.core.schema_discovery import (
        SchemaDiscoveryError,
    )

    client, _ = test_client

    _, token = register_and_login(client)

    org_id, source_id = configured_source(
        client,
        token,
    )

    @contextmanager
    def fake_connection(**kwargs):
        yield object()

    def failed_discovery(connection):
        raise SchemaDiscoveryError(
            "Unable to discover PostgreSQL schema"
        )

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        fake_connection,
    )

    monkeypatch.setattr(
        "app.api.datasources.discover_postgres_schema",
        failed_discovery,
    )

    response = client.get(
        schema_url(org_id, source_id),
        headers=auth(token),
    )

    assert response.status_code == 502

    # Never expose database credentials.
    assert "TestPassword123!" not in response.text
