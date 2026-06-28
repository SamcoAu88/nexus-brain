from pydantic import BaseModel, Field
from uuid import UUID


class SignupRequest(BaseModel):
    """User signup request"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)  # Require 8+ chars for signup


class LoginRequest(BaseModel):
    """User login request"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    """Token response from login/refresh endpoints"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """User profile response"""

    user_id: UUID
    username: str
    is_active: bool

    class Config:
        from_attributes = True
