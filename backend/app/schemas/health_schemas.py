from typing import Literal

from app.schemas.base import APIModel


class HealthResponse(APIModel):
    status: Literal["ok"] = "ok"
    service: str = "agrologistix-api"
    version: str = "0.1.0"
