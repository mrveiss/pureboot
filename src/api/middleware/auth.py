"""Authentication middleware for FastAPI."""
from datetime import datetime

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.api.routes.auth import verify_access_token
from src.db.database import async_session_factory
from src.db.models import ApiKey, User
from src.utils.api_keys import parse_api_key, verify_api_key


# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/boot",
    "/api/v1/ipxe",
    "/api/v1/report",
}

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = (
    "/assets",
    "/api/v1/boot/",
    "/api/v1/ipxe/",
)

# File extensions that don't require authentication (static assets)
PUBLIC_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".css",
    ".js",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
)


def is_public_path(path: str) -> bool:
    """Check if path is public (no auth required)."""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    # Allow static assets by extension
    for ext in PUBLIC_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


async def authenticate_api_key(
    key: str, db: AsyncSession, client_ip: str
) -> tuple[User | None, str | None]:
    """
    Authenticate via API key.

    Returns:
        tuple of (user, error_message)
    """
    parsed = parse_api_key(key)
    if not parsed:
        return None, "Invalid API key format"

    prefix, _ = parsed

    # Look up key by prefix
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_prefix == prefix)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        return None, "API key not found"

    if not api_key.is_active:
        return None, "API key is disabled"

    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None, "API key has expired"

    # Verify the key
    if not verify_api_key(key, api_key.key_hash):
        return None, "Invalid API key"

    # Load the service account
    result = await db.execute(
        select(User).where(User.id == api_key.service_account_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        return None, "Service account not found"

    if not user.is_active:
        return None, "Service account is disabled"

    if user.expires_at and user.expires_at < datetime.utcnow():
        return None, "Service account has expired"

    # Update last used
    await db.execute(
        update(ApiKey)
        .where(ApiKey.id == api_key.id)
        .values(last_used_at=datetime.utcnow(), last_used_ip=client_ip)
    )
    await db.commit()

    return user, None


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication on protected routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Allow public paths
        if is_public_path(path):
            return await call_next(request)

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid authentication scheme"},
            )

        token = auth_header[7:]

        # Check if it's an API key (starts with pb_)
        if token.startswith("pb_"):
            if not async_session_factory:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Database not initialized"},
                )

            client_ip = request.client.host if request.client else "unknown"
            async with async_session_factory() as db:
                user, error = await authenticate_api_key(token, db, client_ip)

                if error:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": error},
                    )

                # Store user info in request state
                request.state.user_id = user.id
                request.state.username = user.username
                request.state.role = user.role
                request.state.auth_method = "api_key"

                return await call_next(request)

        # Otherwise treat as JWT
        payload = verify_access_token(token)

        if not payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Store user info in request state
        request.state.user_id = payload.get("sub")
        request.state.username = payload.get("username")
        request.state.role = payload.get("role")
        request.state.auth_method = "jwt"

        return await call_next(request)
