
import uuid

import pytest
from sqlalchemy import select

from app.core.connection_security import UnsafeDatabaseHostError
from app.models.datasource_credential import DataSourceCredential
from test_datasources import (
    create_organization,
    datasource_url,
    register_and_login,
    test_client,
)


def test_restricted_host_rejected_without_saving_credentials(
    test_client,
    monkeypatch,
):
    client, TestSession = test_client

    _, token = register_and_login(client)
    org_id = create_organization(client, token)

    created = client.post(
        datasource_url(org_id),
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"Restricted-{uuid.uuid4().hex[:8]}"},
    )
    assert created.status_code == 201

    source_id = created.json()["id"]

    # Simulate a host resolving to a restricted destination.
    def reject_host(host):
        raise UnsafeDatabaseHostError(
            "Database host resolves to a restricted IP address"
        )

    monkeypatch.setattr(
        "app.api.datasources.validate_database_host",
        reject_host,
    )

    response = client.put(
        f"{datasource_url(org_id)}/{source_id}/credentials",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "host": "internal.example.com",
            "port": 5432,
            "database_name": "analytics",
            "username": "readonly_user",
            "password": "SecretPassword123!",
        },
    )

    assert response.status_code == 422
    assert "restricted" in response.json()["detail"].lower()

    with TestSession() as session:
        credential = session.scalar(
            select(DataSourceCredential).where(
                DataSourceCredential.data_source_id
                == uuid.UUID(source_id)
            )
        )

        assert credential is None
