
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.schemas.membership import MembershipCreate, MembershipResponse
from app.api.dependencies import get_current_user
from app.api.organization_permissions import require_organization_role
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrganizationCreate, OrganizationResponse


router = APIRouter(tags=["Organizations"])


# --------------------------------------------------
# CREATE ORGANIZATION
# POST /api/v1/organizations
# --------------------------------------------------

@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_organization(
    payload: OrganizationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.scalar(
        select(Organization).where(
            Organization.slug == payload.slug
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        )

    organization = Organization(
        name=payload.name,
        slug=payload.slug,
    )

    try:
        db.add(organization)
        db.flush()

        membership = OrganizationMembership(
            organization_id=organization.id,
            user_id=current_user.id,
            role="owner",
        )

        db.add(membership)
        db.commit()

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        )

    db.refresh(organization)

    return organization


# --------------------------------------------------
# LIST MY ORGANIZATIONS
# GET /api/v1/organizations
# --------------------------------------------------

@router.get(
    "",
    response_model=list[OrganizationResponse],
)
def list_my_organizations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    statement = (
        select(Organization)
        .join(
            OrganizationMembership,
            OrganizationMembership.organization_id == Organization.id,
        )
        .where(
            OrganizationMembership.user_id == current_user.id
        )
        .order_by(
            Organization.created_at.desc(),
            Organization.id,
        )
    )

    return db.scalars(statement).all()


# --------------------------------------------------
# GET ORGANIZATION DETAILS (RBAC PROTECTED)
# GET /api/v1/organizations/{organization_id}
# --------------------------------------------------

@router.get(
    "/{organization_id}",
    response_model=OrganizationResponse,
)
def get_organization(
    organization_id: UUID,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(
        require_organization_role(
            "owner",
            "admin",
            "member",
            "viewer",
        )
    ),
):
    organization = db.get(
        Organization,
        organization_id,
    )

    if organization is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    return organization


# --------------------------------------------------
# LIST ORGANIZATION MEMBERS (OWNER / ADMIN ONLY)
# GET /api/v1/organizations/{organization_id}/members
# --------------------------------------------------

@router.get(
    "/{organization_id}/members",
    response_model=list[MembershipResponse],
)
def list_organization_members(
    organization_id: UUID,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
):
    statement = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.organization_id == organization_id
        )
        .order_by(
            OrganizationMembership.id
        )
    )

    return db.scalars(statement).all()

# --------------------------------------------------
# ADD ORGANIZATION MEMBER (OWNER ONLY)
# POST /api/v1/organizations/{organization_id}/members
# --------------------------------------------------

@router.post(
    "/{organization_id}/members",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_organization_member(
    organization_id: UUID,
    payload: MembershipCreate,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner")
    ),
):
    # Verify the target user exists.
    target_user = db.get(User, payload.user_id)

    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Reject users who are already members.
    existing_membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == payload.user_id,
        )
    )

    if existing_membership is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member",
        )

    new_membership = OrganizationMembership(
        organization_id=organization_id,
        user_id=payload.user_id,
        role=payload.role,
    )

    try:
        db.add(new_membership)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member",
        )

    db.refresh(new_membership)

    return new_membership


# --------------------------------------------------
# REMOVE ORGANIZATION MEMBER (OWNER ONLY)
# DELETE /api/v1/organizations/{organization_id}/members/{user_id}
# --------------------------------------------------

@router.delete(
    "/{organization_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_organization_member(
    organization_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner")
    ),
):
    target_membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
        )
    )

    if target_membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )

    # Never allow removal of an owner through this endpoint.
    if target_membership.role == "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner membership cannot be removed",
        )

    db.delete(target_membership)
    db.commit()
