from uuid import uuid4

import jwt

from app.core.config import get_settings
from app.core.jwt import create_access_token, verify_access_token


def test_create_and_verify_access_token():
    user_id = uuid4()

    token = create_access_token(user_id)

    assert isinstance(token, str)
    assert verify_access_token(token) == user_id


def test_invalid_token_is_rejected():
    assert verify_access_token("invalid.token.value") is None


def test_wrong_token_type_is_rejected():
    settings = get_settings()

    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "refresh",
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm="HS256",
    )

    assert verify_access_token(token) is None


def test_tampered_token_is_rejected():
    token = create_access_token(uuid4())

    parts = token.split(".")
    parts[1] = (
        "A" if parts[1][0] != "A" else "B"
    ) + parts[1][1:]

    tampered_token = ".".join(parts)

    assert verify_access_token(tampered_token) is None