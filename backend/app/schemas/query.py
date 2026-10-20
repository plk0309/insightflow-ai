
from pydantic import BaseModel, Field


class QueryExecuteRequest(BaseModel):
    sql: str = Field(
        min_length=1,
        max_length=20_000,
    )
