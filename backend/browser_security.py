"""Shared browser origin and CORS policy for RESQNET."""

import os
import re

from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware


DEVELOPMENT_ORIGINS = {
    "http://localhost:5173",
    "http://localhost:5174",
}


def configured_frontend_origin():
    """Return a valid configured origin, or None."""

    value = os.getenv("FRONTEND_URL", "").rstrip("/")

    if not value:
        return None

    if any(character.isspace() for character in value):
        return None

    try:
        parsed = urlsplit(value)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError:
        return None

    if (
        not hostname
        or not re.fullmatch(r"[a-z0-9.-]+", hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        return None

    development = (
        os.getenv("RESQNET_ENV") == "development"
    )

    if parsed.scheme != "https":
        if not (
            development
            and parsed.scheme == "http"
            and hostname in {"localhost", "127.0.0.1"}
        ):
            return None

    origin = parsed.scheme + "://" + hostname

    default_port = 443 if parsed.scheme == "https" else 80

    if port is not None and port != default_port:
        origin += ":" + str(port)

    # Accept only a canonical browser origin.
    if value != origin:
        return None

    return origin


def get_trusted_origins():
    """Return exact origins permitted by the browser policy."""

    allowed = set()

    if os.getenv("RESQNET_ENV") == "development":
        allowed.update(DEVELOPMENT_ORIGINS)

    frontend = configured_frontend_origin()

    if frontend:
        allowed.add(frontend)

    return sorted(allowed)


def check_trusted_origin(request: Request) -> None:
    """Reject missing and untrusted request origins."""

    origin = request.headers.get("origin")

    if not origin or origin not in get_trusted_origins():
        raise HTTPException(
            status_code=403,
            detail="Untrusted request origin",
        )


def configure_browser_cors(app: FastAPI) -> None:
    """Install credential-aware CORS using trusted origins."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_trusted_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
