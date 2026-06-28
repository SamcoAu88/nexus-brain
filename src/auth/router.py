from uuid import uuid4
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.auth.tokens import (
    create_access_token,
    create_refresh_token,
    refresh_access_token,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    """Login request with username and password."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    """Token response from login/refresh endpoints."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest) -> TokenResponse:
    """
    Login endpoint. Currently returns demo tokens.

    In production, this should:
    1. Look up user in database by username
    2. Verify password hash
    3. Return tokens for that user
    """
    # TODO: Implement actual user lookup and password verification
    # For now, demo: any username/password works, generates unique user_id
    user_id = uuid4()

    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest) -> TokenResponse:
    """
    Refresh access token using a refresh token.

    Takes a refresh token (valid for 7 days) and returns a new access token.
    """
    new_access_token = refresh_access_token(request.refresh_token)

    if new_access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=request.refresh_token,  # Return same refresh token
    )
