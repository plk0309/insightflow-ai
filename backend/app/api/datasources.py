
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.schema_discovery import (
    SchemaDiscoveryError,
    discover_postgres_schema,
)
from app.core.encryption import decrypt_credential
from app.core.postgres_connection import (
    PostgreSQLConnectionError,
    secure_postgres_connection,
)

from app.api.organization_permissions import require_organization_role
from app.db.session import get_db
from app.models.datasource import DataSource
from app.models.membership import OrganizationMembership
from app.schemas.datasource import (
    DataSourceCreate,
    DataSourceResponse,
)
from app.core.encryption import encrypt_credential
from app.models.datasource_credential import DataSourceCredential
from app.schemas.datasource_credential import (
    DataSourceCredentialCreate,
    DataSourceCredentialResponse,
)
from app.core.connection_security import (
    UnsafeDatabaseHostError,
    validate_database_host,
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

# --------------------------------------------------
# CONFIGURE POSTGRESQL CREDENTIALS
# PUT /api/v1/organizations/{organization_id}/data-sources/{data_source_id}/credentials
# --------------------------------------------------

@router.put(
    "/{data_source_id}/credentials",
    response_model=DataSourceCredentialResponse,
)
def configure_data_source_credentials(
    organization_id: UUID,
    data_source_id: UUID,
    payload: DataSourceCredentialCreate,
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

    if data_source.source_type != "postgresql":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported data source type",
        )


    # Reject restricted database destinations before saving
    # any connection settings.
    try:
        validated_host = validate_database_host(payload.host)
    except UnsafeDatabaseHostError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    encrypted_password = encrypt_credential(
        payload.password.get_secret_value()
    )

    credential = db.scalar(
        select(DataSourceCredential).where(
            DataSourceCredential.data_source_id == data_source_id
        )
    )

    if credential is None:
        credential = DataSourceCredential(
            data_source_id=data_source_id,
            host=validated_host,
            port=payload.port,
            database_name=payload.database_name,
            username=payload.username,
            encrypted_password=encrypted_password,
        )
        db.add(credential)
    else:
        credential.host = validated_host
        credential.port = payload.port
        credential.database_name = payload.database_name
        credential.username = payload.username
        credential.encrypted_password = encrypted_password

    # Credentials have been saved, but connectivity
    # has not yet been verified.
    data_source.status = "not_connected"

    db.commit()

    return DataSourceCredentialResponse(
        message="Credentials saved securely",
        data_source_id=str(data_source_id),
        configured=True,
    )


# --------------------------------------------------
# TEST POSTGRESQL CONNECTION
# POST /api/v1/organizations/{organization_id}/data-sources/{data_source_id}/test-connection
# --------------------------------------------------

@router.post(
    "/{data_source_id}/test-connection",
)
def test_data_source_connection(
    organization_id: UUID,
    data_source_id: UUID,
    db: Session = Depends(get_db),
    membership: OrganizationMembership = Depends(
        require_organization_role("owner", "admin")
    ),
):
    # Restrict lookup to the requested organization.
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

    if data_source.source_type != "postgresql":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported data source type",
        )

    credential = db.scalar(
        select(DataSourceCredential).where(
            DataSourceCredential.data_source_id == data_source.id
        )
    )

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data source credentials are not configured",
        )

    # Do not return encrypted or decrypted passwords.
    try:
        password = decrypt_credential(
            credential.encrypted_password
        )

        with secure_postgres_connection(
            host=credential.host,
            port=credential.port,
            database_name=credential.database_name,
            username=credential.username,
            password=password,
        ) as connection:
            # Execute a minimal, read-only connectivity check.
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

            if result is None or result[0] != 1:
                raise PostgreSQLConnectionError(
                    "Connection verification failed"
                )

    except PostgreSQLConnectionError:
        data_source.status = "connection_failed"
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Secure database connection failed",
        ) from None

    except Exception:
        # Unexpected errors must not expose credentials,
        # connection parameters, or database internals.
        # Do not include exception details in the response.
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection verification failed",
        ) from None

    data_source.status = "connected"
    db.commit()

    return {
        "message": "Database connection verified successfully",
        "data_source_id": str(data_source.id),
        "connected": True,
    }
# --------------------------------------------------
# DISCOVER POSTGRESQL DATABASE SCHEMA
# GET /api/v1/organizations/{organization_id}/data-sources/{data_source_id}/schema
# --------------------------------------------------

@router.get("/{data_source_id}/schema")
def get_data_source_schema(
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
    # Verify the data source belongs to this organization.
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

    if data_source.source_type != "postgresql":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported data source type",
        )

    # Retrieve credentials for this verified data source.
    credential = db.scalar(
        select(DataSourceCredential).where(
            DataSourceCredential.data_source_id == data_source.id
        )
    )

    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Data source credentials are not configured",
        )

    try:
        password = decrypt_credential(
            credential.encrypted_password
        )

        # The connection adapter validates the destination,
        # pins its resolved IP, and requires verified TLS.
        with secure_postgres_connection(
            host=credential.host,
            port=credential.port,
            database_name=credential.database_name,
            username=credential.username,
            password=password,
        ) as connection:
            schema = discover_postgres_schema(connection)

    except (PostgreSQLConnectionError, SchemaDiscoveryError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to discover database schema",
        ) from None

    except Exception:
        # Never expose credentials or database internals.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Schema discovery failed",
        ) from None

    return {
        "data_source_id": str(data_source.id),
        "table_count": schema["table_count"],
        "tables": schema["tables"],
    }