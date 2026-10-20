
from pydantic import BaseModel, Field, SecretStr


class DataSourceCredentialCreate(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(min_length=1, max_length=255)
    username: str = Field(min_length=1, max_length=255)
    password: SecretStr = Field(min_length=1)


class DataSourceCredentialResponse(BaseModel):
    message: str
    data_source_id: str
    configured: bool
