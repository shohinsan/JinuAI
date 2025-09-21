"""Auth Routes
===========
Contains endpoints for user authentication, registration, and access token refresh.

Endpoints:
- POST /login: Authenticate user and return access & refresh tokens.
- POST /register: Register a new user account.
- POST /token: Generate a new access token using a valid refresh token.
"""

from datetime import timedelta

from fastapi import APIRouter, Form, HTTPException, Response, status

from app.utils import security
from app.utils.config import settings
from app.utils.delegate import UserServiceDep
from app.utils.models import (
    EmailPasswordLogin,
    RefreshTokenRequest,
    Token,
    TokenWithRefresh,
    UserPublic,
    UserRegister,
)

router = APIRouter()


@router.post("/login")
def login_with_email_password(
    user_service: UserServiceDep, credentials: EmailPasswordLogin, response: Response
) -> TokenWithRefresh:
    """Authenticate user with email and password"""
    user = user_service.authenticate(credentials.email, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    refresh_token = security.create_refresh_token(user.id)

    response.status_code = status.HTTP_200_OK
    return TokenWithRefresh(access_token=access_token, refresh_token=refresh_token)


@router.post("/register")
def register_user(
    user_service: UserServiceDep,
    response: Response,
    name: str = Form(...),
    account: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
) -> UserPublic:
    """Register a new user"""
    if password != password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match."
        )
    if not security.validate_password(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Does not meet complexity.",
        )

    user_in = UserRegister(name=name, account=account, email=email, password=password)

    try:
        registered_user = user_service.register_user(user_in)
        response.status_code = status.HTTP_201_CREATED
        return registered_user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/token")
def refresh_access_token(request: RefreshTokenRequest, response: Response) -> Token:
    """Get a new access token"""
    user_id = security.verify_refresh_token(request.refresh_token)

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user_id, expires_delta=access_token_expires
    )

    response.status_code = status.HTTP_200_OK
    return Token(access_token=access_token)
