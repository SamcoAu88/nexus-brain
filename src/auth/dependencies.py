from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from src.auth.tokens import verify_token

security = HTTPBearer()


async def get_current_user(
    credentials=Depends(security),
) -> UUID:
    """
    FastAPI dependency to extract and verify user_id from JWT token.

    Usage:
        @router.get("/protected")
        async def protected_endpoint(user_id: UUID = Depends(get_current_user)):
            return {"user_id": user_id}
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    token_data = verify_token(token)

    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_data.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token type must be 'access'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token_data.user_id


async def get_current_user_optional(
    credentials: Optional = Depends(security),
) -> Optional[UUID]:
    """
    Optional version of get_current_user.
    Returns None if no valid token, doesn't raise exception.
    """
    if credentials is None:
        return None

    token = credentials.credentials
    token_data = verify_token(token)

    if token_data is None or token_data.type != "access":
        return None

    return token_data.user_id
