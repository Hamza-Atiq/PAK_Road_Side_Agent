"""Auth API — register, OTP verification, login, refresh, current-user.

Flow:
1. POST /register   -> creates inactive user, triggers OTP (returns user_id)
2. POST /verify-otp -> activates user
3. POST /login      -> only works when is_active = True
4. POST /refresh    -> rotates access token from refresh cookie
5. GET  /me         -> current user profile
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

# Module-level limiter, shared with app.state.limiter via key_func identity
limiter = Limiter(key_func=get_remote_address)
from app.database import get_db
from app.middleware.auth import CurrentUser
from app.middleware.rate_limit import rate_limit
from app.middleware.logging import get_logger
from app.models.enums import UserRole
from app.models.provider import Provider
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    VerifyOTPRequest,
)
from app.services.jwt_service import (
    InvalidTokenError,
    decode_token,
    encode_access_token,
    encode_refresh_token,
)
from app.services.security import hash_password, verify_password
from app.services.twilio_verify import OTPSendError, check_otp, send_otp

log = get_logger("auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "roadside_refresh"


def _refresh_cookie_max_age() -> int:
    return settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        max_age=_refresh_cookie_max_age(),
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path="/api/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


def _build_token_response(user: User) -> TokenResponse:
    access = encode_access_token(user_id=user.id, role=user.role, phone=user.phone)
    refresh = encode_refresh_token(user_id=user.id, role=user.role, phone=user.phone)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


# ----------------------------------------------------------------------
# POST /register
# ----------------------------------------------------------------------


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a customer or provider account",
)
@rate_limit(limiter, settings.RATE_LIMIT_AUTH)
async def register(
    request: Request,
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    # Phone uniqueness
    existing = await db.scalar(select(User).where(User.phone == payload.phone))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this phone number already exists",
        )

    user = User(
        phone=payload.phone,
        name=payload.name,
        email=payload.email,
        role=payload.role.value,
        password_hash=hash_password(payload.password),
        is_active=False,           # inactive until OTP verified
        is_phone_verified=False,
    )
    db.add(user)
    await db.flush()

    # Provider role gets a provider profile row too
    if payload.role == UserRole.provider:
        if not payload.service_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="service_type is required for provider registration",
            )
        provider = Provider(
            id=user.id,
            service_type=payload.service_type,
            vehicle_info=payload.vehicle_info,
            is_available=False,
            is_approved=False,
        )
        db.add(provider)

    try:
        await send_otp(payload.phone)
    except OTPSendError as exc:
        # OTP send failed — roll back so the user can retry from scratch
        await db.rollback()
        log.error("otp_send_failed", phone=payload.phone, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send verification code. Please try again.",
        ) from exc

    log.info(
        "user_registered",
        user_id=str(user.id),
        role=user.role,
        phone=payload.phone,
        ip=get_remote_address(request),
    )
    return MessageResponse(
        message=f"Verification code sent to {payload.phone}. Submit it via /verify-otp."
    )


# ----------------------------------------------------------------------
# POST /verify-otp
# ----------------------------------------------------------------------


@router.post(
    "/verify-otp",
    response_model=TokenResponse,
    summary="Verify OTP code and activate account",
)
@rate_limit(limiter, settings.RATE_LIMIT_AUTH)
async def verify_otp(
    request: Request,
    response: Response,
    payload: VerifyOTPRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    user = await db.scalar(select(User).where(User.phone == payload.phone))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No registration found for this phone number",
        )
    if user.is_phone_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone number is already verified. Please log in.",
        )

    approved = await check_otp(payload.phone, payload.code)
    if not approved:
        log.warning("otp_check_failed", phone=payload.phone, user_id=str(user.id))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user.is_phone_verified = True
    user.is_active = True
    user.updated_at = datetime.utcnow()

    token_response = _build_token_response(user)
    _set_refresh_cookie(response, token_response.refresh_token)
    log.info("user_verified", user_id=str(user.id), phone=user.phone)
    return token_response


# ----------------------------------------------------------------------
# POST /login
# ----------------------------------------------------------------------


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with phone + password",
)
@rate_limit(limiter, settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    user = await db.scalar(select(User).where(User.phone == payload.phone))

    # Constant-ish time: always run verify_password even when user is None
    valid = verify_password(payload.password, user.password_hash) if user else False

    if not user or not valid:
        log.warning(
            "login_failed_credentials",
            phone=payload.phone,
            ip=get_remote_address(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone or password",
        )

    if not user.is_phone_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Phone number not verified. Please complete OTP verification.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended. Contact support.",
        )

    token_response = _build_token_response(user)
    _set_refresh_cookie(response, token_response.refresh_token)
    log.info(
        "login_success",
        user_id=str(user.id),
        role=user.role,
        ip=get_remote_address(request),
    )
    return token_response


# ----------------------------------------------------------------------
# POST /refresh
# ----------------------------------------------------------------------


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Issue a new access token from a refresh token",
)
async def refresh_tokens(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    roadside_refresh: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if not roadside_refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token cookie",
        )
    try:
        payload = decode_token(roadside_refresh, expected_type="refresh")
    except InvalidTokenError as exc:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {exc}",
        ) from exc

    import uuid as _uuid
    user = await db.get(User, _uuid.UUID(payload.sub))
    if user is None or not user.is_active:
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer active",
        )

    token_response = _build_token_response(user)
    _set_refresh_cookie(response, token_response.refresh_token)
    return token_response


# ----------------------------------------------------------------------
# GET /me
# ----------------------------------------------------------------------


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Return the currently authenticated user",
)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


# ----------------------------------------------------------------------
# POST /logout
# ----------------------------------------------------------------------


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Clear refresh cookie",
)
async def logout(response: Response) -> MessageResponse:
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out")
