from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.core.config import get_settings


def create_access_token(user_id: UUID) -> str:
    settings = get_settings()

    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        ),
        "type": "access",
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm="HS256",
    )


def verify_access_token(token: str) -> UUID | None:
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "iat", "exp"]},
        )

        if payload.get("type") != "access":
            return None

        return UUID(payload["sub"])

    except (InvalidTokenError, ValueError, TypeError):
        return None