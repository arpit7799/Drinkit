"""HTTP routes for customer authentication and identity."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.auth import User
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.modules.auth.service import (
    IssuedTokens,
    login_user,
    logout_session,
    refresh_session,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(issued: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        user=UserResponse.model_validate(issued.user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Register an account and establish its first authenticated session."""

    return _token_response(await register_user(session, request))


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate an account with email and password."""

    return _token_response(await login_user(session, request))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Rotate a refresh token and issue a new access token."""

    return _token_response(await refresh_session(session, request.refresh_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: LogoutRequest,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Revoke the presented refresh token without revealing its existence."""

    await logout_session(session, request.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the authenticated user's non-sensitive profile."""

    return UserResponse.model_validate(current_user)
