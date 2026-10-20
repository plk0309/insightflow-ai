
import uuid
from pathlib import Path

import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app
from app.models.membership import OrganizationMembership
from app.models.organization import Organization


@pytest.fixture
def test_client():
    test_url = dotenv_values(
        Path(__file__).resolve().parents[1] / ".env.test"
    ).get("DATABASE_URL")

    if not test_url:
        pytest.fail("DATABASE_URL missing from backend/.env.test")

    if make_url(test_url).database != "insightflow_test":
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


def register_and_login(client):
    email = f"owner-{uuid.uuid4().hex}@example.com"
    password = "SecureTestPassword123!"

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "full_name": "Organization Owner",
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

    return (
        registration.json()["id"],
        login.json()["access_token"],
    )


def test_create_organization_and_owner_membership(test_client):
    client, TestSession = test_client

    user_id, token = register_and_login(client)
    slug = f"test-org-{uuid.uuid4().hex}"

    response = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Test Analytics Organization",
            "slug": slug,
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Test Analytics Organization"
    assert data["slug"] == slug
    assert "id" in data
    assert "created_at" in data

    with TestSession() as session:
        organization = session.scalar(
            select(Organization).where(
                Organization.slug == slug
            )
        )

        assert organization is not None

        memberships = session.scalars(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id
                == organization.id
            )
        ).all()

        assert len(memberships) == 1
        assert str(memberships[0].user_id) == user_id
        assert memberships[0].role == "owner"


def test_create_organization_without_token(test_client):
    client, _ = test_client

    response = client.post(
        "/api/v1/organizations",
        json={
            "name": "Unauthorized Organization",
            "slug": f"unauthorized-{uuid.uuid4().hex}",
        },
    )

    assert response.status_code == 401


def test_duplicate_organization_slug_rejected(test_client):
    client, _ = test_client

    _, token = register_and_login(client)
    slug = f"duplicate-org-{uuid.uuid4().hex}"

    payload = {
        "name": "First Organization",
        "slug": slug,
    }

    headers = {"Authorization": f"Bearer {token}"}

    first_response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json=payload,
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/api/v1/organizations",
        headers=headers,
        json=payload,
    )

    assert second_response.status_code == 409


def test_invalid_organization_slug_rejected(test_client):
    client, _ = test_client

    _, token = register_and_login(client)

    response = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Invalid Slug Organization",
            "slug": "Invalid Slug!",
        },
    )

    assert response.status_code == 422


def test_list_only_my_organizations(test_client):
    client, _ = test_client

    # Register two separate users.
    user_a_id, token_a = register_and_login(client)
    user_b_id, token_b = register_and_login(client)

    assert user_a_id != user_b_id

    slug_a = f"tenant-a-{uuid.uuid4().hex}"
    slug_b = f"tenant-b-{uuid.uuid4().hex}"

    # User A creates an organization.
    response_a = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Tenant A Organization",
            "slug": slug_a,
        },
    )
    assert response_a.status_code == 201

    # User B creates a different organization.
    response_b = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "name": "Tenant B Organization",
            "slug": slug_b,
        },
    )
    assert response_b.status_code == 201

    # User A must only see their own organization.
    list_a = client.get(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_a}"},
    )

    assert list_a.status_code == 200

    slugs_a = {org["slug"] for org in list_a.json()}

    assert slug_a in slugs_a
    assert slug_b not in slugs_a

    # User B must only see their own organization.
    list_b = client.get(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert list_b.status_code == 200

    slugs_b = {org["slug"] for org in list_b.json()}

    assert slug_b in slugs_b
    assert slug_a not in slugs_b


def test_list_organizations_without_token(test_client):
    client, _ = test_client

    response = client.get("/api/v1/organizations")

    assert response.status_code == 401


def test_list_organizations_with_invalid_token(test_client):
    client, _ = test_client

    response = client.get(
        "/api/v1/organizations",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_get_own_organization(test_client):
    client, _ = test_client

    _, token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "My Organization",
            "slug": f"my-org-{uuid.uuid4().hex}",
        },
    )

    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == organization_id
    assert response.json()["name"] == "My Organization"


def test_cannot_access_another_users_organization(test_client):
    client, _ = test_client

    _, token_a = register_and_login(client)
    _, token_b = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "name": "Private Organization",
            "slug": f"private-org-{uuid.uuid4().hex}",
        },
    )

    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


def test_get_nonexistent_organization(test_client):
    client, _ = test_client

    _, token = register_and_login(client)

    nonexistent_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/organizations/{nonexistent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_organization_without_token(test_client):
    client, _ = test_client

    response = client.get(
        f"/api/v1/organizations/{uuid.uuid4()}"
    )

    assert response.status_code == 401


def test_owner_can_list_organization_members(test_client):
    client, _ = test_client

    user_id, token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Owner Membership Test",
            "slug": f"owner-members-{uuid.uuid4().hex}",
        },
    )

    assert created.status_code == 201
    organization_id = created.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    members = response.json()
    assert len(members) == 1
    assert members[0]["user_id"] == user_id
    assert members[0]["role"] == "owner"


def test_nonmember_cannot_list_organization_members(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    _, outsider_token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Private Membership Test",
            "slug": f"private-members-{uuid.uuid4().hex}",
        },
    )

    assert created.status_code == 201
    organization_id = created.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 404


def test_viewer_cannot_list_organization_members(test_client):
    client, TestSession = test_client

    _, owner_token = register_and_login(client)
    viewer_id, viewer_token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Viewer Permission Test",
            "slug": f"viewer-members-{uuid.uuid4().hex}",
        },
    )

    assert created.status_code == 201
    organization_id = created.json()["id"]

    with TestSession() as session:
        session.add(
            OrganizationMembership(
                organization_id=uuid.UUID(organization_id),
                user_id=uuid.UUID(viewer_id),
                role="viewer",
            )
        )
        session.commit()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 403


def test_admin_can_list_organization_members(test_client):
    client, TestSession = test_client

    _, owner_token = register_and_login(client)
    admin_id, admin_token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Admin Permission Test",
            "slug": f"admin-members-{uuid.uuid4().hex}",
        },
    )

    assert created.status_code == 201
    organization_id = created.json()["id"]

    with TestSession() as session:
        session.add(
            OrganizationMembership(
                organization_id=uuid.UUID(organization_id),
                user_id=uuid.UUID(admin_id),
                role="admin",
            )
        )
        session.commit()

    response = client.get(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200

    member_ids = {
        member["user_id"]
        for member in response.json()
    }

    assert admin_id in member_ids


def test_members_endpoint_requires_authentication(test_client):
    client, _ = test_client

    response = client.get(
        f"/api/v1/organizations/{uuid.uuid4()}/members"
    )

    assert response.status_code == 401


def test_owner_can_add_organization_member(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    new_user_id, _ = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Member Creation Test",
            "slug": f"add-member-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": new_user_id,
            "role": "viewer",
        },
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == new_user_id
    assert response.json()["role"] == "viewer"
    assert response.json()["organization_id"] == organization_id


def test_cannot_add_duplicate_member(test_client):
    client, _ = test_client

    owner_id, owner_token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Duplicate Member Test",
            "slug": f"duplicate-member-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": owner_id,
            "role": "viewer",
        },
    )

    assert response.status_code == 409


def test_cannot_assign_owner_role(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    new_user_id, _ = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Owner Role Protection",
            "slug": f"owner-protection-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": new_user_id,
            "role": "owner",
        },
    )

    assert response.status_code == 422


def test_admin_cannot_add_organization_member(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    admin_id, admin_token = register_and_login(client)
    target_user_id, _ = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Admin Member Restriction",
            "slug": f"admin-restriction-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]

    # Owner adds the admin.
    admin_added = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "user_id": admin_id,
            "role": "admin",
        },
    )
    assert admin_added.status_code == 201

    # Admin attempts to add another member.
    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "user_id": target_user_id,
            "role": "viewer",
        },
    )

    assert response.status_code == 403


def test_nonmember_cannot_add_organization_member(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    _, outsider_token = register_and_login(client)
    target_user_id, _ = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Cross Tenant Member Protection",
            "slug": f"cross-tenant-member-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{organization_id}/members",
        headers={"Authorization": f"Bearer {outsider_token}"},
        json={
            "user_id": target_user_id,
            "role": "viewer",
        },
    )

    assert response.status_code == 404


def test_add_member_requires_authentication(test_client):
    client, _ = test_client

    response = client.post(
        f"/api/v1/organizations/{uuid.uuid4()}/members",
        json={
            "user_id": str(uuid.uuid4()),
            "role": "viewer",
        },
    )

    assert response.status_code == 401


def test_owner_can_remove_organization_member(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    member_id, _ = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Member Removal Test",
            "slug": f"remove-member-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]
    members_url = f"/api/v1/organizations/{organization_id}/members"
    headers = {"Authorization": f"Bearer {owner_token}"}

    added = client.post(
        members_url,
        headers=headers,
        json={"user_id": member_id, "role": "viewer"},
    )
    assert added.status_code == 201

    response = client.delete(
        f"{members_url}/{member_id}",
        headers=headers,
    )

    assert response.status_code == 204

    listed = client.get(members_url, headers=headers)
    assert listed.status_code == 200
    assert member_id not in {
        member["user_id"] for member in listed.json()
    }


def test_owner_cannot_remove_owner_membership(test_client):
    client, _ = test_client

    owner_id, owner_token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Owner Removal Protection",
            "slug": f"protect-owner-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/members/{owner_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 403

    # The owner must retain access after the rejected removal.
    detail = client.get(
        f"/api/v1/organizations/{organization_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert detail.status_code == 200


def test_admin_cannot_remove_organization_member(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    admin_id, admin_token = register_and_login(client)
    target_id, _ = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Admin Removal Restriction",
            "slug": f"admin-remove-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]
    members_url = f"/api/v1/organizations/{organization_id}/members"
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    for user_id, role in [
        (admin_id, "admin"),
        (target_id, "viewer"),
    ]:
        added = client.post(
            members_url,
            headers=owner_headers,
            json={"user_id": user_id, "role": role},
        )
        assert added.status_code == 201

    response = client.delete(
        f"{members_url}/{target_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 403

    listed = client.get(members_url, headers=owner_headers)
    assert target_id in {
        member["user_id"] for member in listed.json()
    }


def test_nonmember_cannot_remove_organization_member(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)
    _, outsider_token = register_and_login(client)
    target_id, _ = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Cross Tenant Removal Protection",
            "slug": f"cross-remove-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]
    members_url = f"/api/v1/organizations/{organization_id}/members"

    added = client.post(
        members_url,
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"user_id": target_id, "role": "viewer"},
    )
    assert added.status_code == 201

    response = client.delete(
        f"{members_url}/{target_id}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 404


def test_remove_nonexistent_membership(test_client):
    client, _ = test_client

    _, owner_token = register_and_login(client)

    created = client.post(
        "/api/v1/organizations",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "name": "Missing Membership Test",
            "slug": f"missing-member-{uuid.uuid4().hex}",
        },
    )
    assert created.status_code == 201

    organization_id = created.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{organization_id}/members/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 404


def test_remove_member_requires_authentication(test_client):
    client, _ = test_client

    response = client.delete(
        f"/api/v1/organizations/{uuid.uuid4()}/members/{uuid.uuid4()}"
    )

    assert response.status_code == 401
