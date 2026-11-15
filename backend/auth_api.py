
"""Individual account authentication API for RESQNET.

Not mounted in main.py until security testing is complete.
"""

import os
import ipaddress
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from account_service import authenticate_user
from database import SessionLocal
from session_service import create_session
from session_tokens import SESSION_LIFETIME
from rate_limit_service import (
    acquire_login_attempt_locks,
    login_block_remaining_seconds,
    record_failed_login,
)

def get_login_client_ip(request: Request) -> str:
    """Return the client IP from trusted ASGI connection data.

    Never read X-Forwarded-For directly from request headers.
    Reverse-proxy trust must be configured at the ASGI server.
    """
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

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=128)


def check_login_origin(request: Request) -> None:
    """Accept login requests only from configured browser origins."""
    allowed = set()

    frontend = os.getenv("FRONTEND_URL", "").rstrip("/")
    if frontend:
        allowed.add(frontend)

    if os.getenv("RESQNET_ENV") == "development":
        allowed.update({
            "http://localhost:5173",
            "http://localhost:5174",
        })

    origin = request.headers.get("origin")

    if not origin or origin not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Untrusted request origin",
        )


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
    user_info = None

    with SessionLocal.begin() as session:
        # Serialize attempts sharing a username or IP.
        acquire_login_attempt_locks(
            session,
            credentials.username,
            client_ip,
        )

        # Check the limit while holding both identity locks.
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
                # The transaction must commit this failure.
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

    if token is None or user_info is None:
        raise RuntimeError(
            "Login did not produce an authenticated session"
        )

    # Issue the cookie only after successful commit.
    response.set_cookie(
        key="resqnet_session",
        value=token,
        httponly=True,
        secure=os.getenv("RESQNET_ENV") != "development",
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
    )

    return {
        "message": "Login successful",
        "user": user_info,
    }
