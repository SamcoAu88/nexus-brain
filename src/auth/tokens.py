from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from pydantic import BaseModel

from src.core.config import settings


class TokenData(BaseModel):
    user_id: UUID
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"


def create_access_token(user_id: UUID, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived access token (default 1 hour)."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(hours=1)

    to_encode = {
        "user_id": str(user_id),
        "exp": expire,
        "iat": now,
        "type": "access",
    }
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(user_id: UUID) -> str:
    """Create a long-lived refresh token (7 days)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=7)

    to_encode = {
        "user_id": str(user_id),
        "exp": expire,
        "iat": now,
        "type": "refresh",
    }
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """Verify and decode JWT token. Returns TokenData if valid, None if invalid."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("user_id")
        if user_id is None:
            return None

        token_data = TokenData(
            user_id=UUID(user_id),
            exp=datetime.fromtimestamp(payload.get("exp"), tz=timezone.utc),
            iat=datetime.fromtimestamp(payload.get("iat"), tz=timezone.utc),
            type=payload.get("type", "access"),
        )
        return token_data
    except (JWTError, ValueError):
        return None


def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Exchange a refresh token for a new access token."""
    token_data = verify_token(refresh_token)
    if token_data is None or token_data.type != "refresh":
        return None

    return create_access_token(token_data.user_id)
