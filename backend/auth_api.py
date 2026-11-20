"""Individual account authentication API for RESQNET.

Not mounted in main.py until security testing is complete.
"""

import os
import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from account_service import (
    authenticate_user,
    normalize_username,
)
from session_authorization import (
    SessionPrincipal,
    get_current_principal,
)
from database import SessionLocal
from session_service import (
    create_session,
    revoke_session,
    get_authenticated_user,
)
from session_tokens import SESSION_LIFETIME
from csrf_protection import (
    generate_csrf_token,
    verify_csrf_token,
    check_trusted_origin as check_login_origin,
)
from rate_limit_service import (
    acquire_login_attempt_locks,
    login_block_remaining_seconds,
    record_failed_login,
)


def get_login_client_ip(request: Request) -> str:
    """Return the client IP from trusted ASGI connection data."""

    client = request.client

    if client is None:
        raise HTTPException(
            status_code=503,
            detail="Client address unavailable",
        )

    try:
        return str(ipaddress.ip_address(client.host))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=503,
            detail="Invalid client address",
        )


class SafeAuthRoute(APIRoute):
    """Prevent authentication validation errors leaking input values."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def safe_handler(request: Request):
            try:
                return await original_handler(request)

            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": "Invalid authentication request",
                    },
                    headers={
                        "Cache-Control": "no-store",
                    },
                )

        return safe_handler


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    route_class=SafeAuthRoute,
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        """Normalize and validate before rate limiting."""
        return normalize_username(value)

    @field_validator("password")
    @classmethod
    def validate_password_encoding(cls, value: str) -> str:
        """Reject malformed Unicode before password verification."""
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("Invalid password encoding") from None

        return value




@router.post("/login")
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
):
    """Authenticate with PostgreSQL-backed login protection."""

    check_login_origin(request)
    client_ip = get_login_client_ip(request)

    blocked_seconds = 0
    invalid_credentials = False
    token = None
    csrf_token = None
    user_info = None

    with SessionLocal.begin() as session:
        acquire_login_attempt_locks(
            session,
            credentials.username,
            client_ip,
        )

        blocked_seconds = login_block_remaining_seconds(
            session,
            credentials.username,
            client_ip,
        )

        if blocked_seconds == 0:
            user = authenticate_user(
                session,
                credentials.username,
                credentials.password,
            )

            if user is None:
                record_failed_login(
                    session,
                    credentials.username,
                    client_ip,
                )

                invalid_credentials = True

            else:
                token = create_session(
                    session,
                    user.id,
                )

                # Generate before commit so a missing CSRF key
                # causes the entire transaction to roll back.
                csrf_token = generate_csrf_token(token)

                user_info = {
                    "id": user.id,
                    "username": user.username,
                    "role": user.role,
                }

    # The transaction has now committed successfully.

    if blocked_seconds > 0:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={
                "Retry-After": str(blocked_seconds),
            },
        )

    if invalid_credentials:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    if token is None or csrf_token is None or user_info is None:
        raise RuntimeError(
            "Login did not produce an authenticated session"
        )

    response.set_cookie(
        key="resqnet_session",
        value=token,
        httponly=True,
        secure=os.getenv("RESQNET_ENV") != "development",
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
    )

    response.headers["Cache-Control"] = "no-store"

    return {
        "message": "Login successful",
        "user": user_info,
        "csrf_token": csrf_token,
    }


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    """Revoke the current session and clear its browser cookie."""

    check_login_origin(request)

    token = request.cookies.get("resqnet_session")

    if token:
        with SessionLocal.begin() as session:
            user = get_authenticated_user(session, token)

            if user is not None:
                submitted_token = request.headers.get(
                    "X-CSRF-Token"
                )

                if not verify_csrf_token(
                    token,
                    submitted_token,
                ):
                    raise HTTPException(
                        status_code=403,
                        detail="Invalid or missing CSRF token",
                    )

                revoke_session(session, token)

    response = Response(status_code=204)

    response.delete_cookie(
        key="resqnet_session",
        path="/",
        httponly=True,
        secure=os.getenv("RESQNET_ENV") != "development",
        samesite="lax",
    )

    return response


@router.post(
    "/session",
    dependencies=[Depends(check_login_origin)],
)
def session_profile(
    request: Request,
    response: Response,
    principal: SessionPrincipal = Depends(
        get_current_principal
    ),
):
    """Restore browser authentication state without creating a session."""

    token = request.cookies.get("resqnet_session")

    csrf_token = generate_csrf_token(token)

    response.headers["Cache-Control"] = "no-store"

    return {
        "user": {
            "id": principal.user_id,
            "username": principal.username,
            "role": principal.role,
        },
        "csrf_token": csrf_token,
    }
