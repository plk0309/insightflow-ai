
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.encryption import decrypt_credential
from app.models.datasource_credential import DataSourceCredential
from test_datasources import (
    create_organization,
    datasource_url,
    register_and_login,
    test_client,
)


@pytest.fixture(autouse=True)
def isolated_encryption_key(monkeypatch):
    """Use a temporary test key, never the real application key."""
    monkeypatch.setenv(
        "CREDENTIAL_ENCRYPTION_KEY",
        Fernet.generate_key().decode("ascii"),
    )


@pytest.fixture(autouse=True)
def mock_host_validation(monkeypatch):
    """Avoid real DNS lookups in credential API tests."""
    monkeypatch.setattr(
        "app.api.datasources.validate_database_host",
        lambda host: host,
    )


def credential_url(org_id, source_id):
    return f"{datasource_url(org_id)}/{source_id}/credentials"


def create_source(client, org_id, token):
    response = client.post(
        datasource_url(org_id),
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"Database-{uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def credential_payload(password="TestPassword123!"):
    return {
        "host": "db.example.com",
        "port": 5432,
        "database_name": "analytics",
        "username": "readonly_user",
        "password": password,
    }


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_owner_saves_encrypted_credentials(test_client):
    client, TestSession = test_client

    _, token = register_and_login(client)
    org_id = create_organization(client, token)
    source_id = create_source(client, org_id, token)

    password = "VerySecretPassword123!"

    response = client.put(
        credential_url(org_id, source_id),
        headers=auth(token),
        json=credential_payload(password),
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True

    # Neither plaintext nor encrypted password may be returned.
    assert "password" not in response.text.lower()
    assert password not in response.text

    with TestSession() as session:
        credential = session.scalar(
            select(DataSourceCredential).where(
                DataSourceCredential.data_source_id
                == uuid.UUID(source_id)
            )
        )

        assert credential is not None
        assert credential.encrypted_password != password
        assert decrypt_credential(
            credential.encrypted_password
        ) == password


def test_credentials_can_be_rotated(test_client):
    client, TestSession = test_client

    _, token = register_and_login(client)
    org_id = create_organization(client, token)
    source_id = create_source(client, org_id, token)

    url = credential_url(org_id, source_id)

    first = client.put(
        url,
        headers=auth(token),
        json=credential_payload("OldPassword123!"),
    )
    assert first.status_code == 200

    second = client.put(
        url,
        headers=auth(token),
        json=credential_payload("NewPassword456!"),
    )
    assert second.status_code == 200

    with TestSession() as session:
        credentials = session.scalars(
            select(DataSourceCredential).where(
                DataSourceCredential.data_source_id
                == uuid.UUID(source_id)
            )
        ).all()

        assert len(credentials) == 1
        assert decrypt_credential(
            credentials[0].encrypted_password
        ) == "NewPassword456!"


def test_admin_can_configure_credentials(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    admin_id, admin_token = register_and_login(client)

    org_id = create_organization(client, owner_token)
    source_id = create_source(client, org_id, owner_token)

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth(owner_token),
        json={"user_id": admin_id, "role": "admin"},
    )
    assert added.status_code == 201

    response = client.put(
        credential_url(org_id, source_id),
        headers=auth(admin_token),
        json=credential_payload(),
    )

    assert response.status_code == 200


def test_viewer_cannot_configure_credentials(test_client):
    client, TestSession = test_client

    _, owner_token = register_and_login(client)
    viewer_id, viewer_token = register_and_login(client)

    org_id = create_organization(client, owner_token)
    source_id = create_source(client, org_id, owner_token)

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth(owner_token),
        json={"user_id": viewer_id, "role": "viewer"},
    )
    assert added.status_code == 201

    response = client.put(
        credential_url(org_id, source_id),
        headers=auth(viewer_token),
        json=credential_payload(),
    )

    assert response.status_code == 403

    with TestSession() as session:
        credential = session.scalar(
            select(DataSourceCredential).where(
                DataSourceCredential.data_source_id
                == uuid.UUID(source_id)
            )
        )
        assert credential is None


def test_cross_tenant_credentials_denied(test_client):
    client, TestSession = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(client, token_a)
    org_b = create_organization(client, token_b)

    source_b = create_source(client, org_b, token_b)

    # Cannot access another organization's endpoint.
    response = client.put(
        credential_url(org_b, source_b),
        headers=auth(token_a),
        json=credential_payload(),
    )
    assert response.status_code == 404

    # Cannot bypass isolation using your own organization ID.
    response = client.put(
        credential_url(org_a, source_b),
        headers=auth(token_a),
        json=credential_payload(),
    )
    assert response.status_code == 404

    with TestSession() as session:
        credential = session.scalar(
            select(DataSourceCredential).where(
                DataSourceCredential.data_source_id
                == uuid.UUID(source_b)
            )
        )
        assert credential is None


def test_credentials_require_authentication(test_client):
    client, _ = test_client

    response = client.put(
        credential_url(uuid.uuid4(), uuid.uuid4()),
        json=credential_payload(),
    )

    assert response.status_code == 401


def test_invalid_credential_port_rejected(test_client):
    client, _ = test_client

    _, token = register_and_login(client)
    org_id = create_organization(client, token)
    source_id = create_source(client, org_id, token)

    payload = credential_payload()
    payload["port"] = 70000

    response = client.put(
        credential_url(org_id, source_id),
        headers=auth(token),
        json=payload,
    )

    assert response.status_code == 422
