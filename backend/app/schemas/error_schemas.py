from pydantic import Field

from app.schemas.base import APIModel


class APIErrorResponse(APIModel):
    code: str
    detail: str
    request_id: str | None = None


class ValidationErrorResponse(APIModel):
    code: str = "validation_error"
    detail: str
    fields: dict[str, list[str]] = Field(default_factory=dict)
    request_id: str | None = None
