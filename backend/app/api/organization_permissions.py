
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.membership import OrganizationMembership
from app.models.user import User


VALID_ROLES = frozenset({
    "owner",
    "admin",
    "member",
    "viewer",
})


def require_organization_role(*allowed_roles: str):
    if not allowed_roles:
        raise ValueError("At least one allowed role is required")

    if not set(allowed_roles).issubset(VALID_ROLES):
        raise ValueError("Unknown organization role")

    def check_permission(
        organization_id: UUID,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> OrganizationMembership:
        membership = db.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id
                == organization_id,
                OrganizationMembership.user_id
                == current_user.id,
            )
        )

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
            )

        if membership.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient organization permissions",
            )

        return membership

    return check_permission
