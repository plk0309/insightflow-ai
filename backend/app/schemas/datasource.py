
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataSourceCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=255,
    )

    source_type: Literal["postgresql"] = "postgresql"


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    source_type: str
    status: str
    created_at: datetime
    updated_at: datetime
