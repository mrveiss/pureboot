"""Authentication API endpoints."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.db.models import User, RefreshToken

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False

try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False

router = APIRouter()

# Configuration
JWT_SECRET = "pureboot-secret-key-change-in-production"  # TODO: Move to config
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRY_MINUTES = 15
REFRESH_TOKEN_EXPIRY_DAYS = 7
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


# --- Schemas ---

class LoginRequest(BaseModel):
    """Login request."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    """User response."""
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool
    last_login_at: str | None
    created_at: str


class ApiResponse(BaseModel):
    """Generic API response."""
    success: bool = True
    message: str | None = None
    data: UserResponse | TokenResponse | None = None


# --- Helper Functions ---

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # Fallback to SHA256 (less secure, but works without bcrypt)
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    if BCRYPT_AVAILABLE and password_hash.startswith("$2"):
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    # Fallback to SHA256
    return hashlib.sha256(password.encode()).hexdigest() == password_hash


def create_access_token(user_id: str, username: str, role: str) -> tuple[str, int]:
    """Create a JWT access token."""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRY_MINUTES)
    expires_in = ACCESS_TOKEN_EXPIRY_MINUTES * 60

    if JWT_AVAILABLE:
        payload = {
            "sub": user_id,
            "username": username,
            "role": role,
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return token, expires_in

    # Fallback: simple token (less secure)
    token = f"{user_id}:{username}:{role}:{int(expires_at.timestamp())}"
    return token, expires_in


def verify_access_token(token: str) -> dict | None:
    """Verify and decode a JWT access token."""
    if JWT_AVAILABLE:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    # Fallback: simple token
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        user_id, username, role, exp = parts
        if int(exp) < datetime.now(timezone.utc).timestamp():
            return None
        return {"sub": user_id, "username": username, "role": role}
    except (ValueError, IndexError):
        return None


def create_refresh_token() -> str:
    """Create a secure refresh token."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# --- Dependency ---

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get the current authenticated user from the Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]  # Remove "Bearer "
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(
        select(User).where(User.id == payload["sub"])
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")

    return user


async def require_role(*roles: str):
    """Dependency factory to require specific roles."""
    async def check_role(user: User = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check_role


# --- Endpoints ---

@router.post("/auth/login", response_model=ApiResponse)
async def login(
    data: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return tokens."""
    # Find user
    result = await db.execute(
        select(User).where(User.username == data.username)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check if locked
    if user.locked_until and datetime.now(timezone.utc) < user.locked_until.replace(tzinfo=timezone.utc):
        remaining = (user.locked_until.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).seconds // 60
        raise HTTPException(
            status_code=423,
            detail=f"Account locked. Try again in {remaining} minutes."
        )

    # Check if active
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account disabled")

    # Verify password
    if not verify_password(data.password, user.password_hash):
        # Increment failed attempts
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        await db.flush()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Reset failed attempts
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    # Create tokens
    access_token, expires_in = create_access_token(user.id, user.username, user.role)
    refresh_token = create_refresh_token()

    # Store refresh token
    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS),
    )
    db.add(refresh_token_record)
    await db.flush()

    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRY_DAYS * 24 * 60 * 60,
    )

    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
        ),
        message="Login successful",
    )


@router.post("/auth/logout", response_model=ApiResponse)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Logout and invalidate refresh token."""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        token_hash = hash_refresh_token(refresh_token)
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        token_record = result.scalar_one_or_none()
        if token_record:
            await db.delete(token_record)
            await db.flush()

    response.delete_cookie("refresh_token")
    return ApiResponse(message="Logged out successfully")


@router.post("/auth/refresh", response_model=ApiResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    token_hash = hash_refresh_token(refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if datetime.now(timezone.utc) > token_record.expires_at.replace(tzinfo=timezone.utc):
        await db.delete(token_record)
        await db.flush()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Get user
    result = await db.execute(
        select(User).where(User.id == token_record.user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        await db.delete(token_record)
        await db.flush()
        raise HTTPException(status_code=401, detail="User not found or disabled")

    # Create new access token
    access_token, expires_in = create_access_token(user.id, user.username, user.role)

    # Rotate refresh token
    new_refresh_token = create_refresh_token()
    token_record.token_hash = hash_refresh_token(new_refresh_token)
    token_record.expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRY_DAYS)
    await db.flush()

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRY_DAYS * 24 * 60 * 60,
    )

    return ApiResponse(
        data=TokenResponse(
            access_token=access_token,
            expires_in=expires_in,
        ),
        message="Token refreshed",
    )


@router.get("/auth/me", response_model=ApiResponse)
async def get_current_user_info(
    user: User = Depends(get_current_user),
):
    """Get current authenticated user info."""
    return ApiResponse(
        data=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
            created_at=user.created_at.isoformat() if user.created_at else "",
        ),
    )
