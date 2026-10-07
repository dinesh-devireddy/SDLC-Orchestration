from datetime import datetime, timezone
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator

RESERVED = {"api", "health", "docs", "redoc", "openapi.json"}
Alias = Annotated[str, Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")]


class CreateURL(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: Annotated[HttpUrl, Field(max_length=2048)]
    alias: Alias | None = None
    expires_at: AwareDatetime | None = None

    @field_validator("destination")
    @classmethod
    def no_credentials(cls, value):
        if value.username or value.password:
            raise ValueError("Destination credentials are not allowed")
        return value

    @field_validator("alias")
    @classmethod
    def allowed_alias(cls, value):
        if value in RESERVED:
            raise ValueError("Alias is reserved")
        return value

    @field_validator("expires_at")
    @classmethod
    def normalize_utc(cls, value):
        return value.astimezone(timezone.utc) if value else None


class URLInfo(BaseModel):
    code: str
    short_url: str
    destination: str
    created_at: datetime
    expires_at: datetime | None
    clicks: int


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
