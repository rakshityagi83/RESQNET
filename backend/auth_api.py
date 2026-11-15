
"""Individual account authentication API for RESQNET.

Not mounted in main.py until security testing is complete.
"""

import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from account_service import authenticate_user
from database import SessionLocal
from session_service import create_session
from session_tokens import SESSION_LIFETIME


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
    """Verify credentials and issue a database-backed session."""
    check_login_origin(request)

    with SessionLocal.begin() as session:
        user = authenticate_user(
            session,
            credentials.username,
            credentials.password,
        )

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid username or password",
            )

        token = create_session(session, user.id)

        user_info = {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        }

    # This runs only after the transaction commits successfully.
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
