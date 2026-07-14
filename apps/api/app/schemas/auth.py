from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=12, max_length=256)


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthenticatedUser
