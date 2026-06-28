from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.auth.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse
from src.auth.password import hash_password, verify_password
from src.auth.tokens import (
    create_access_token,
    create_refresh_token,
    refresh_access_token,
)
from src.core.database import SessionLocal
from src.models.memory import UserProfile

router = APIRouter(prefix="/auth", tags=["authentication"])


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/signup", response_model=UserResponse)
async def signup(
    request: SignupRequest, db: Session = Depends(get_db)
) -> UserResponse:
    """
    Create a new user account.

    Returns user profile on success, 400 if username already taken.
    """
    # Check if username already exists
    existing_user = db.query(UserProfile).filter_by(username=request.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    # Hash password and create user
    password_hash = hash_password(request.password)
    user = UserProfile(username=request.username, password_hash=password_hash)

    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        user_id=user.user_id,
        username=user.username,
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """
    Login with username and password.

    Returns access and refresh tokens on success, 401 if credentials invalid.
    """
    # Look up user by username
    user = db.query(UserProfile).filter_by(username=request.username).first()

    # Verify user exists and password is correct
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Generate tokens
    access_token = create_access_token(user.user_id)
    refresh_token = create_refresh_token(user.user_id)

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
