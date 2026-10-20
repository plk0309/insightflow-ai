from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.jwt import create_access_token
from app.core.security import verify_password
from app.schemas.auth import UserLogin, TokenResponse

from app.core.security import hash_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserRegister, UserResponse

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.jwt import verify_access_token


router = APIRouter(tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_user(
    payload: UserRegister,
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower()

    existing_user = db.scalar(
        select(User).where(User.email == email)
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    db.refresh(user)

    return user

@router.post(
    "/login",
    response_model=TokenResponse,
)
def login_user(
    payload: UserLogin,
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if (
        user is None
        or user.hashed_password is None
        or not verify_password(
            payload.password,
            user.hashed_password,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user.id)

    return TokenResponse(access_token=access_token)

bearer_scheme = HTTPBearer(auto_error=False)


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    user_id = verify_access_token(credentials.credentials)

    if user_id is None:
        raise unauthorized

    user = db.get(User, user_id)

    if user is None:
        raise unauthorized

    return user