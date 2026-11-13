
import os
import secrets

from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized():
    raise HTTPException(
        status_code=401,
        detail="Authentication required or invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_role(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
) -> str:
    # Reject missing credentials before accessing application data.
    if credentials is None or not credentials.credentials:
        unauthorized()

    admin_token = os.getenv("RESQNET_ADMIN_TOKEN", "")
    operator_token = os.getenv("RESQNET_OPERATOR_TOKEN", "")

    # Fail closed if credentials have not been securely configured.
    if (
        len(admin_token) < 32
        or len(operator_token) < 32
        or secrets.compare_digest(admin_token, operator_token)
    ):
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured",
        )

    provided_token = credentials.credentials

    if secrets.compare_digest(provided_token, admin_token):
        return "admin"

    if secrets.compare_digest(provided_token, operator_token):
        return "operator"

    unauthorized()


def require_admin(
    role: str = Depends(get_current_role),
) -> str:
    if role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin permission required",
        )

    return role


def require_operator(
    role: str = Depends(get_current_role),
) -> str:
    if role not in {"operator", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Operator permission required",
        )

    return role
