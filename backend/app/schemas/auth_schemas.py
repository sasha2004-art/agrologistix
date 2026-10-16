from pydantic import model_validator

from app.schemas.base import APIModel
from app.schemas.enums import AuthRole


class AuthResponse(APIModel):
    role: AuthRole
    is_admin: bool
    access_pin_valid: bool = True

    @model_validator(mode="after")
    def validate_admin_role(self) -> "AuthResponse":
        expected_admin = self.role is AuthRole.ADMIN
        if self.is_admin != expected_admin:
            raise ValueError("is_admin must match the response role")
        return self
