
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class MembershipCreate(BaseModel):
    user_id: UUID
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        allowed_roles = {"admin", "member", "viewer"}

        if value not in allowed_roles:
            raise ValueError(
                "Role must be admin, member, or viewer"
            )

        return value


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
