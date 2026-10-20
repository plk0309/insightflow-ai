
import uuid

from app.models.datasource import DataSource
from tests.test_organizations import (
    register_and_login,
    test_client,
)


def create_organization(client, token):
    response = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "DataSource Test Organization",
            "slug": f"datasource-{uuid.uuid4().hex}",
        },
    )

    assert response.status_code == 201
    return response.json()["id"]


def datasource_url(organization_id):
    return (
        f"/api/v1/organizations/"
        f"{organization_id}/data-sources"
    )


def test_owner_can_create_data_source(test_client):
    client, TestSession = test_client

    _, owner_token = register_and_login(client)
    organization_id = create_organization(client, owner_token)

    response = client.post(
        datasource_url(organization_id),
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Sales Database",
            "source_type": "postgresql",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Sales Database"
    assert data["source_type"] == "postgresql"
    assert data["status"] == "not_connected"
    assert data["organization_id"] == organization_id

    with TestSession() as session:
        data_source = session.get(
            DataSource,
            uuid.UUID(data["id"]),
        )

        assert data_source is not None
        assert str(data_source.organization_id) == organization_id


def test_duplicate_data_source_name_rejected(test_client):
    client, _ = test_client

    _, token = register_and_login(client)
    organization_id = create_organization(client, token)

    url = datasource_url(organization_id)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "name": "Finance Database",
        "source_type": "postgresql",
    }

    first = client.post(url, headers=headers, json=payload)
    second = client.post(url, headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 409


def test_different_organizations_can_use_same_name(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(client, token_a)
    org_b = create_organization(client, token_b)

    payload = {
        "name": "Shared Database Name",
        "source_type": "postgresql",
    }

    response_a = client.post(
        datasource_url(org_a),
        headers={"Authorization": f"Bearer {token_a}"},
        json=payload,
    )

    response_b = client.post(
        datasource_url(org_b),
        headers={"Authorization": f"Bearer {token_b}"},
        json=payload,
    )

    assert response_a.status_code == 201
    assert response_b.status_code == 201

    assert response_a.json()["id"] != response_b.json()["id"]


def test_admin_can_create_data_source(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    admin_id, admin_token = register_and_login(client)

    organization_id = create_organization(client, owner_token)

    added = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": admin_id,
            "role": "admin",
        },
    )

    assert added.status_code == 201

    response = client.post(
        datasource_url(organization_id),
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Admin Database"},
    )

    assert response.status_code == 201


def test_viewer_cannot_create_data_source(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    viewer_id, viewer_token = register_and_login(client)

    organization_id = create_organization(client, owner_token)

    added = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": viewer_id,
            "role": "viewer",
        },
    )

    assert added.status_code == 201

    response = client.post(
        datasource_url(organization_id),
        headers={"Authorization": f"Bearer {viewer_token}"},
        json={"name": "Forbidden Database"},
    )

    assert response.status_code == 403


def test_nonmember_cannot_create_data_source(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    _, outsider_token = register_and_login(client)

    organization_id = create_organization(client, owner_token)

    response = client.post(
        datasource_url(organization_id),
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={"name": "Unauthorized Database"},
    )

    assert response.status_code == 404


def test_data_source_creation_requires_authentication(test_client):
    client, _ = test_client

    response = client.post(
        datasource_url(uuid.uuid4()),
        json={"name": "No Authentication Database"},
    )

    assert response.status_code == 401


# --------------------------------------------------
# DATA SOURCE LISTING SECURITY TESTS
# --------------------------------------------------


def test_owner_can_list_data_sources(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    organization_id = create_organization(client, owner_token)

    url = datasource_url(organization_id)
    headers = {"Authorization": f"Bearer {owner_token}"}

    # Create two data sources.
    for name in ["Sales Database", "Finance Database"]:
        response = client.post(
            url,
            headers=headers,
            json={
                "name": name,
                "source_type": "postgresql",
            },
        )
        assert response.status_code == 201

    # Retrieve the organization's data sources.
    response = client.get(url, headers=headers)

    assert response.status_code == 200

    data_sources = response.json()

    assert len(data_sources) == 2

    names = {source["name"] for source in data_sources}

    assert names == {
        "Sales Database",
        "Finance Database",
    }


def test_viewer_can_list_data_sources(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    viewer_id, viewer_token = register_and_login(client)

    organization_id = create_organization(client, owner_token)

    # Owner creates a data source.
    created = client.post(
        datasource_url(organization_id),
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Viewer Accessible Database"},
    )

    assert created.status_code == 201

    # Owner adds the viewer to the organization.
    added = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": viewer_id,
            "role": "viewer",
        },
    )

    assert added.status_code == 201

    # Viewer can list the organization's data sources.
    response = client.get(
        datasource_url(organization_id),
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Viewer Accessible Database"


def test_data_source_listing_is_tenant_isolated(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(client, token_a)
    org_b = create_organization(client, token_b)

    # Each organization creates its own data source.
    created_a = client.post(
        datasource_url(org_a),
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "Tenant A Database"},
    )

    created_b = client.post(
        datasource_url(org_b),
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Tenant B Database"},
    )

    assert created_a.status_code == 201
    assert created_b.status_code == 201

    # Each owner sees only their organization's data sources.
    list_a = client.get(
        datasource_url(org_a),
        headers={"Authorization": f"Bearer {token_a}"},
    )

    list_b = client.get(
        datasource_url(org_b),
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert list_a.status_code == 200
    assert list_b.status_code == 200

    assert {source["name"] for source in list_a.json()} == {
        "Tenant A Database"
    }

    assert {source["name"] for source in list_b.json()} == {
        "Tenant B Database"
    }

    # Cross-tenant access must be denied.
    forbidden = client.get(
        datasource_url(org_b),
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert forbidden.status_code == 404


def test_data_source_listing_requires_authentication(test_client):
    client, _ = test_client

    response = client.get(
        datasource_url(uuid.uuid4())
    )

    assert response.status_code == 401


# --------------------------------------------------
# DATA SOURCE DETAIL SECURITY TESTS
# --------------------------------------------------


def test_owner_can_get_data_source_details(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    organization_id = create_organization(client, owner_token)

    headers = {"Authorization": f"Bearer {owner_token}"}

    created = client.post(
        datasource_url(organization_id),
        headers=headers,
        json={"name": "Sales Analytics Database"},
    )

    assert created.status_code == 201

    data_source_id = created.json()["id"]

    response = client.get(
        f"{datasource_url(organization_id)}/{data_source_id}",
        headers=headers,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == data_source_id
    assert data["organization_id"] == organization_id
    assert data["name"] == "Sales Analytics Database"
    assert data["source_type"] == "postgresql"
    assert data["status"] == "not_connected"


def test_viewer_can_get_data_source_details(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    viewer_id, viewer_token = register_and_login(client)

    organization_id = create_organization(client, owner_token)

    created = client.post(
        datasource_url(organization_id),
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Viewer Readable Database"},
    )

    assert created.status_code == 201
    data_source_id = created.json()["id"]

    added = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": viewer_id,
            "role": "viewer",
        },
    )

    assert added.status_code == 201

    response = client.get(
        f"{datasource_url(organization_id)}/{data_source_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == data_source_id


def test_cross_tenant_data_source_details_denied(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(client, token_a)
    org_b = create_organization(client, token_b)

    created = client.post(
        datasource_url(org_b),
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Tenant B Secret Database"},
    )

    assert created.status_code == 201

    data_source_id = created.json()["id"]

    # User A cannot access organization B.
    response = client.get(
        f"{datasource_url(org_b)}/{data_source_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 404

    # Even with access to organization A, user A cannot
    # retrieve a data source belonging to organization B.
    response = client.get(
        f"{datasource_url(org_a)}/{data_source_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert response.status_code == 404


def test_nonexistent_data_source_returns_404(test_client):
    client, _ = test_client

    _, token = register_and_login(client)
    organization_id = create_organization(client, token)

    nonexistent_id = uuid.uuid4()

    response = client.get(
        f"{datasource_url(organization_id)}/{nonexistent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_data_source_details_require_authentication(test_client):
    client, _ = test_client

    response = client.get(
        f"{datasource_url(uuid.uuid4())}/{uuid.uuid4()}"
    )

    assert response.status_code == 401


# --------------------------------------------------
# DATA SOURCE DELETION SECURITY TESTS
# --------------------------------------------------


def test_owner_can_delete_data_source(test_client):
    client, _ = test_client

    _, token = register_and_login(client)
    org_id = create_organization(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        datasource_url(org_id),
        headers=headers,
        json={"name": "Delete Me Database"},
    )
    assert created.status_code == 201

    source_id = created.json()["id"]
    detail_url = f"{datasource_url(org_id)}/{source_id}"

    deleted = client.delete(detail_url, headers=headers)

    assert deleted.status_code == 204
    assert deleted.content == b""

    # The record must no longer be accessible.
    retrieved = client.get(detail_url, headers=headers)
    assert retrieved.status_code == 404


def test_admin_can_delete_data_source(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    admin_id, admin_token = register_and_login(client)

    org_id = create_organization(client, owner_token)

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": admin_id, "role": "admin"},
    )
    assert added.status_code == 201

    created = client.post(
        datasource_url(org_id),
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Admin Deletable Database"},
    )
    assert created.status_code == 201

    response = client.delete(
        f"{datasource_url(org_id)}/{created.json()['id']}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 204


def test_viewer_cannot_delete_data_source(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    viewer_id, viewer_token = register_and_login(client)

    org_id = create_organization(client, owner_token)

    added = client.post(
        f"/api/v1/organizations/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": viewer_id, "role": "viewer"},
    )
    assert added.status_code == 201

    created = client.post(
        datasource_url(org_id),
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"name": "Protected Database"},
    )
    assert created.status_code == 201

    detail_url = f"{datasource_url(org_id)}/{created.json()['id']}"

    response = client.delete(
        detail_url,
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 403

    # The rejected deletion must not remove the record.
    retrieved = client.get(
        detail_url,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert retrieved.status_code == 200


def test_cross_tenant_data_source_deletion_denied(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    org_a = create_organization(client, token_a)
    org_b = create_organization(client, token_b)

    created = client.post(
        datasource_url(org_b),
        headers={"Authorization": f"Bearer {token_b}"},
        json={"name": "Tenant B Protected Database"},
    )
    assert created.status_code == 201

    source_id = created.json()["id"]

    # Tenant A cannot delete through Tenant B's organization.
    response = client.delete(
        f"{datasource_url(org_b)}/{source_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404

    # Tenant A also cannot delete Tenant B's record
    # by supplying Tenant A's organization ID.
    response = client.delete(
        f"{datasource_url(org_a)}/{source_id}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 404

    # Tenant B's record must still exist.
    retrieved = client.get(
        f"{datasource_url(org_b)}/{source_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert retrieved.status_code == 200


def test_nonexistent_data_source_deletion_returns_404(test_client):
    client, _ = test_client

    _, token = register_and_login(client)
    org_id = create_organization(client, token)

    response = client.delete(
        f"{datasource_url(org_id)}/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_data_source_deletion_requires_authentication(test_client):
    client, _ = test_client

    response = client.delete(
        f"{datasource_url(uuid.uuid4())}/{uuid.uuid4()}"
    )

    assert response.status_code == 401
