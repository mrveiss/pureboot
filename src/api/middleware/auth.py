"""Authentication middleware for FastAPI."""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.api.routes.auth import verify_access_token


# Paths that don't require authentication
PUBLIC_PATHS = {
    "/",
    "/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/boot",  # PXE boot endpoints
    "/api/v1/ipxe",  # iPXE endpoints
    "/api/v1/report",  # Node reporting
}

# Path prefixes that don't require authentication
PUBLIC_PREFIXES = (
    "/assets",
    "/api/v1/boot/",
    "/api/v1/ipxe/",
)


def is_public_path(path: str) -> bool:
    """Check if path is public (no auth required)."""
    if path in PUBLIC_PATHS:
        return True
    for prefix in PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


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
        payload = verify_access_token(token)

        if not payload:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Store user info in request state for downstream use
        request.state.user_id = payload.get("sub")
        request.state.username = payload.get("username")
        request.state.role = payload.get("role")

        return await call_next(request)
