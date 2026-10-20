
from contextlib import contextmanager
import uuid

import pytest
from cryptography.fernet import Fernet

from app.core.postgres_connection import PostgreSQLConnectionError
from app.core.query_execution import QueryExecutionError
from test_datasource_connection_api import (
    auth,
    configured_source,
    create_organization,
    create_source,
    register_and_login,
    test_client,
)


SAMPLE_RESULT = {
    "columns": ["region", "revenue"],
    "rows": [["North", "12500.50"]],
    "row_count": 1,
    "truncated": False,
}


@pytest.fixture(autouse=True)
def isolated_query_api_test(monkeypatch):
    # Use a temporary encryption key and no real DNS.
    monkeypatch.setenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )

    monkeypatch.setattr(
        "app.api.datasources.validate_database_host",
        lambda host: host,
    )

    # Prevent accidental external database connections.
    @contextmanager
    def blocked_connection(**kwargs):
        raise AssertionError("Unexpected database connection")
        yield

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        blocked_connection,
    )


def query_url(org_id, source_id):
    return (
        f"/api/v1/organizations/{org_id}"
        f"/data-sources/{source_id}/query"
    )


def mock_query_execution(monkeypatch):
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
        "app.api.datasources.execute_read_only_query",
        lambda connection, sql: SAMPLE_RESULT,
    )

    return calls


def test_owner_can_execute_query(test_client, monkeypatch):
    client, _ = test_client
    _, token = register_and_login(client)
    org_id, source_id = configured_source(client, token)

    calls = mock_query_execution(monkeypatch)

    response = client.post(
        query_url(org_id, source_id),
        headers=auth(token),
        json={"sql": "SELECT region, revenue FROM sales"},
    )

    assert response.status_code == 200

    result = response.json()

    assert result["data_source_id"] == str(source_id)
    assert result["columns"] == SAMPLE_RESULT["columns"]
    assert result["rows"] == SAMPLE_RESULT["rows"]
    assert len(calls) == 1

    assert "TestPassword123!" not in response.text


@pytest.mark.parametrize("role", ["admin", "member"])
def test_authorized_roles_can_execute_query(
    test_client, monkeypatch, role
):
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

    mock_query_execution(monkeypatch)

    response = client.post(
        query_url(org_id, source_id),
        headers=auth(user_token),
        json={"sql": "SELECT COUNT(*) FROM sales"},
    )

    assert response.status_code == 200


def test_viewer_cannot_execute_query(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    viewer_id, viewer_token = register_and_login(client)

    org_id, source_id = configured_source(client, owner_token)

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth(owner_token),
        json={"user_id": viewer_id, "role": "viewer"},
    )
    assert added.status_code == 201

    response = client.post(
        query_url(org_id, source_id),
        headers=auth(viewer_token),
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 403


def test_query_requires_authentication(test_client):
    client, _ = test_client

    response = client.post(
        query_url(uuid.uuid4(), uuid.uuid4()),
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 401


def test_cross_tenant_query_denied(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(client, token_a)
    org_b, source_b = configured_source(client, token_b)

    response = client.post(
        query_url(org_b, source_b),
        headers=auth(token_a),
        json={"sql": "SELECT 1"},
    )
    assert response.status_code == 404

    response = client.post(
        query_url(org_a, source_b),
        headers=auth(token_a),
        json={"sql": "SELECT 1"},
    )
    assert response.status_code == 404


def test_unsafe_sql_rejected_without_connection(test_client):
    client, _ = test_client
    _, token = register_and_login(client)
    org_id, source_id = configured_source(client, token)

    response = client.post(
        query_url(org_id, source_id),
        headers=auth(token),
        json={"sql": "DROP TABLE customers"},
    )

    assert response.status_code == 422


def test_missing_credentials_rejected(test_client):
    client, _ = test_client
    _, token = register_and_login(client)

    org_id = create_organization(client, token)
    source_id = create_source(client, org_id, token)

    response = client.post(
        query_url(org_id, source_id),
        headers=auth(token),
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 400


def test_connection_failure_is_sanitized(
    test_client, monkeypatch
):
    client, _ = test_client
    _, token = register_and_login(client)
    org_id, source_id = configured_source(client, token)

    @contextmanager
    def failed_connection(**kwargs):
        raise PostgreSQLConnectionError(
            "Sensitive connection information"
        )
        yield

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        failed_connection,
    )

    response = client.post(
        query_url(org_id, source_id),
        headers=auth(token),
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 502
    assert "Sensitive connection information" not in response.text
    assert "TestPassword123!" not in response.text


def test_query_failure_is_sanitized(test_client, monkeypatch):
    client, _ = test_client
    _, token = register_and_login(client)
    org_id, source_id = configured_source(client, token)

    @contextmanager
    def fake_connection(**kwargs):
        yield object()

    monkeypatch.setattr(
        "app.api.datasources.secure_postgres_connection",
        fake_connection,
    )

    def fail_query(connection, sql):
        raise QueryExecutionError("Sensitive database information")

    monkeypatch.setattr(
        "app.api.datasources.execute_read_only_query",
        fail_query,
    )

    response = client.post(
        query_url(org_id, source_id),
        headers=auth(token),
        json={"sql": "SELECT 1"},
    )

    assert response.status_code == 422
    assert "Sensitive database information" not in response.text
    assert "TestPassword123!" not in response.text
