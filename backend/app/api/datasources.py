
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.organization_permissions import require_organization_role
from app.db.session import get_db
from app.models.datasource import DataSource
from app.models.membership import OrganizationMembership
from app.schemas.datasource import (
    DataSourceCreate,
    DataSourceResponse,
)


router = APIRouter(tags=["Data Sources"])


# --------------------------------------------------
# REGISTER DATA SOURCE (OWNER / ADMIN ONLY)
# POST /api/v1/organizations/{organization_id}/data-sources
# --------------------------------------------------

@router.post(
    "",
    response_model=DataSourceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_data_source(
    organization_id: UUID,
    payload: DataSourceCreate,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
):
    existing = db.scalar(
        select(DataSource).where(
            DataSource.organization_id == organization_id,
            DataSource.name == payload.name,
        )
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Data source name already exists",
        )

    data_source = DataSource(
        organization_id=organization_id,
        name=payload.name,
        source_type=payload.source_type,
        status="not_connected",
    )

    try:
        db.add(data_source)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Data source name already exists",
        )

    db.refresh(data_source)

    return data_source


# --------------------------------------------------
# LIST ORGANIZATION DATA SOURCES
# GET /api/v1/organizations/{organization_id}/data-sources
# --------------------------------------------------

@router.get(
    "",
    response_model=list[DataSourceResponse],
)
def list_organization_data_sources(
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
    statement = (
        select(DataSource)
        .where(
            DataSource.organization_id == organization_id
        )
        .order_by(
            DataSource.created_at.desc(),
            DataSource.id,
        )
    )

    return db.scalars(statement).all()


# --------------------------------------------------
# GET INDIVIDUAL DATA SOURCE
# GET /api/v1/organizations/{organization_id}/data-sources/{data_source_id}
# --------------------------------------------------

@router.get(
    "/{data_source_id}",
    response_model=DataSourceResponse,
)
def get_data_source(
    organization_id: UUID,
    data_source_id: UUID,
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
    data_source = db.scalar(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization_id,
        )
    )

    if data_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    return data_source


# --------------------------------------------------
# DELETE DATA SOURCE
# DELETE /api/v1/organizations/{organization_id}/data-sources/{data_source_id}
# --------------------------------------------------

@router.delete(
    "/{data_source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_data_source(
    organization_id: UUID,
    data_source_id: UUID,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
):
    data_source = db.scalar(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization_id,
        )
    )

    if data_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Data source not found",
        )

    db.delete(data_source)
    db.commit()

    return None
