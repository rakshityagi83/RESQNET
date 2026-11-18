"""Individual session-based authorization for RESQNET."""

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from database import SessionLocal
from csrf_protection import (
    check_trusted_origin,
    verify_csrf_token,
)
from session_service import (
    get_authenticated_user,
    valid_token_format,
)


@dataclass(frozen=True)
class SessionPrincipal:
    """Authenticated account identity without sensitive credentials."""

    user_id: int
    username: str
    role: str


def get_current_principal(request: Request) -> SessionPrincipal:
    """Resolve the authenticated account from its session cookie."""

    token = request.cookies.get("resqnet_session")

    if not valid_token_format(token):
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )

    with SessionLocal() as db:
        user = get_authenticated_user(db, token)

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired session",
            )

        if user.role not in {"admin", "operator"}:
            raise HTTPException(
                status_code=403,
                detail="Invalid account role",
            )

        return SessionPrincipal(
            user_id=user.id,
            username=user.username,
            role=user.role,
        )


def require_session_admin(
    principal: SessionPrincipal = Depends(get_current_principal),
) -> SessionPrincipal:
    """Require an authenticated administrator."""

    if principal.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin permission required",
        )

    return principal


def require_session_operator(
    principal: SessionPrincipal = Depends(get_current_principal),
) -> SessionPrincipal:
    """Allow authenticated operators and administrators."""

    if principal.role not in {"operator", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Operator permission required",
        )

    return principal



def require_csrf_principal(
    request: Request,
    principal: SessionPrincipal = Depends(get_current_principal),
) -> SessionPrincipal:
    """Require authentication, trusted origin and session-bound CSRF."""

    check_trusted_origin(request)

    token = request.cookies.get("resqnet_session")
    submitted_token = request.headers.get("X-CSRF-Token")

    if not verify_csrf_token(token, submitted_token):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing CSRF token",
        )

    return principal


def require_admin_write(
    principal: SessionPrincipal = Depends(require_csrf_principal),
) -> SessionPrincipal:
    """Protect administrative write operations."""

    return require_session_admin(principal)


def require_operator_write(
    principal: SessionPrincipal = Depends(require_csrf_principal),
) -> SessionPrincipal:
    """Protect operator-level write operations."""

    return require_session_operator(principal)
