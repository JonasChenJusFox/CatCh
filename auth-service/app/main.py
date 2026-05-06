"""Auth Service for CatCh.

This service owns username/password authentication and JWT creation. It only
describes the authenticated user's role; gameplay permissions are enforced by
downstream services.
"""

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
import os
import re
import secrets

import jwt
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from pymongo import MongoClient
from pymongo.errors import PyMongoError

MONGO_URL = os.getenv("MONGO_URL", "")
MONGO_DB = os.getenv("MONGO_DB", "fish_likes_cat")

JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "210000"))
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,"
    "http://localhost:5175,http://localhost:3000",
)
BUILD_VERSION = os.getenv("BUILD_VERSION", "auth-password-v1")

UserRole = Literal["kitten", "cat"]

# In-memory fallback for local tests and development without Mongo.
local_users: dict[str, dict] = {}
mongo_client = (
    MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000) if MONGO_URL else None
)


class SignUpRequest(BaseModel):
    """Request body for creating a username/password account."""

    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr
    role: UserRole = Field(default="kitten")


class LoginRequest(BaseModel):
    """Request body for signing in with username and password."""

    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    """Request body for resetting a password."""

    username: str = Field(min_length=2, max_length=40)
    email: EmailStr
    new_password: str = Field(min_length=8, max_length=128)


class SimpleStatusResponse(BaseModel):
    """Generic success response."""

    success: bool
    message: str


class AuthResponse(BaseModel):
    """Authentication response returned after a successful login."""

    token: str
    user_id: str
    username: str
    email: EmailStr
    role: UserRole
    expires_at: str
    token_system_enabled: bool
    permissions: list[str]


class TokenRefreshRequest(BaseModel):
    """Request body for refreshing an existing JWT."""

    token: str


class VerifyTokenRequest(BaseModel):
    """Request body for checking whether a JWT is valid."""

    token: str


class TokenValidationResponse(BaseModel):
    """Response body for token validation requests."""

    valid: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    expires_at: Optional[str] = None
    token_system_enabled: bool = False
    permissions: list[str] = []


def permissions_for_role(role: UserRole) -> list[str]:
    """Return the permission names granted to a CatCh user role."""

    if role == "cat":
        return [
            "create_public_pond",
            "create_private_pond",
            "manage_pond_problems",
            "send_room_code_invites",
            "manage_assignments",
        ]
    return [
        "join_pond",
        "solve_problem",
        "earn_fishing_chance",
        "fish",
        "manage_aquarium",
        "use_marketplace",
        "use_cat_can_tokens",
        "vote_on_public_pond",
    ]


def token_system_enabled(role: UserRole) -> bool:
    """Return whether a CatCh role participates in Cat Can Tokens."""

    return role == "kitten"


def users_collection():
    """Return the shared users collection when Mongo is configured."""

    if mongo_client is None:
        return None
    return mongo_client[MONGO_DB].users


def mongo_unavailable_error() -> HTTPException:
    """Return a stable API error for MongoDB connectivity failures."""

    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication database is unavailable",
    )


def utc_now() -> datetime:
    """Return an aware UTC datetime for token and code timestamps."""

    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize MongoDB datetimes to aware UTC datetimes."""

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_username(username: str) -> str:
    """Create a display-safe username from user input."""

    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", username.strip()).strip("_")
    if len(cleaned) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username must contain at least 2 letters, numbers, underscores, or hyphens",
        )
    return cleaned[:40]


def username_key(username: str) -> str:
    """Return the case-insensitive lookup key for a username."""

    return normalize_username(username).lower()


def hash_password(password: str) -> str:
    """Return a PBKDF2 password hash safe for storage."""

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    encoded_salt = base64.b64encode(salt).decode("ascii")
    encoded_digest = base64.b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${encoded_salt}${encoded_digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Return whether a password matches a stored PBKDF2 hash."""

    try:
        algorithm, iterations, encoded_salt, encoded_digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(encoded_salt.encode("ascii"))
        expected = base64.b64decode(encoded_digest.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iterations),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def find_user_by_username(username: str) -> Optional[dict]:
    """Return a user profile by username from Mongo or local storage."""

    key = username_key(username)
    collection = users_collection()
    if collection is None:
        return local_users.get(key)

    try:
        return collection.find_one({"username_key": key})
    except PyMongoError as exc:
        print(f"Mongo user lookup error: {exc}")
        raise mongo_unavailable_error() from exc


def create_user(username: str, email: str, password: str, role: UserRole) -> dict:
    """Create and persist a username/password user profile."""

    display_name = normalize_username(username)
    key = display_name.lower()
    if find_user_by_username(display_name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already taken",
        )

    now = utc_now()
    user_id = f"{role}_{int(now.timestamp() * 1000)}"
    profile = {
        "_id": user_id,
        "user_id": user_id,
        "username": display_name,
        "username_key": key,
        "email": email,
        "role": role,
        "password_hash": hash_password(password),
        "created_at": now,
        "last_login_at": now,
    }

    collection = users_collection()
    if collection is None:
        local_users[key] = profile
        return profile

    try:
        collection.insert_one(profile)
        return profile
    except PyMongoError as exc:
        print(f"Mongo user create error: {exc}")
        raise mongo_unavailable_error() from exc


def update_user_login(user: dict) -> None:
    """Persist a successful login timestamp."""

    collection = users_collection()
    if collection is None:
        user["last_login_at"] = utc_now()
        return

    try:
        collection.update_one(
            {"_id": user["_id"]}, {"$set": {"last_login_at": utc_now()}}
        )
    except PyMongoError as exc:
        print(f"Mongo user login update error: {exc}")
        raise mongo_unavailable_error() from exc


def update_user_password(user: dict, new_password: str) -> dict:
    """Replace a user's password hash."""

    password_hash = hash_password(new_password)
    collection = users_collection()
    if collection is None:
        user["password_hash"] = password_hash
        user["password_reset_at"] = utc_now()
        return user

    try:
        collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"password_hash": password_hash, "password_reset_at": utc_now()}},
        )
        updated = find_user_by_username(user["username"])
        return updated or {**user, "password_hash": password_hash}
    except PyMongoError as exc:
        print(f"Mongo password reset error: {exc}")
        raise mongo_unavailable_error() from exc


def authenticate_user(username: str, password: str) -> dict:
    """Validate username/password credentials and return the user profile."""

    user = find_user_by_username(username)
    if not user or not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    update_user_login(user)
    return user


def auth_response_for_user(user: dict) -> AuthResponse:
    """Create a JWT auth response for an existing user profile."""

    role: UserRole = user.get("role", "kitten")
    user_id = str(user.get("user_id") or user.get("_id"))
    token, expiry = create_jwt_token(
        user_id,
        user["email"],
        role,
        user["username"],
    )
    return AuthResponse(
        token=token,
        user_id=user_id,
        username=user["username"],
        email=user["email"],
        role=role,
        expires_at=expiry.isoformat(),
        token_system_enabled=token_system_enabled(role),
        permissions=permissions_for_role(role),
    )


def create_jwt_token(
    user_id: str,
    email: str,
    role: UserRole,
    username: str,
) -> tuple[str, datetime]:
    """Create a role-aware JWT and return it with its expiration time."""

    now = utc_now()
    expiry = now + timedelta(hours=JWT_EXPIRY_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "username": username,
        "role": role,
        "token_system_enabled": token_system_enabled(role),
        "permissions": permissions_for_role(role),
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
        "iss": "auth-service",
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expiry


def verify_jwt_token(token: str) -> Optional[dict]:
    """Decode a JWT and return None when it is expired or invalid."""

    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


app = FastAPI(
    title="Auth Service",
    description="CatCh username/password authentication and role-aware JWT generation",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unexpected_error_handler(_request: Request, exc: Exception):
    """Return debuggable errors instead of opaque platform 500 pages."""

    print(f"Unexpected auth-service error: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"{type(exc).__name__}: {exc}"},
    )


@app.get("/health", tags=["health"])
def health():
    """Return service health information."""

    return {
        "status": "ok",
        "service": "auth-service",
        "version": BUILD_VERSION,
        "mongo_enabled": mongo_client is not None,
    }


@app.get("/auth/roles", tags=["auth"])
def roles():
    """Return the available CatCh roles and their permissions."""

    return {
        "roles": {
            "kitten": {
                "description": "Student gameplay user",
                "token_system_enabled": True,
                "permissions": permissions_for_role("kitten"),
            },
            "cat": {
                "description": "Teacher and problem creator",
                "token_system_enabled": False,
                "permissions": permissions_for_role("cat"),
            },
        }
    }


@app.post("/auth/signup", response_model=AuthResponse, tags=["auth"])
def signup_endpoint(request: SignUpRequest):
    """Create a username/password account and issue a JWT."""

    user = create_user(
        request.username,
        str(request.email),
        request.password,
        request.role,
    )
    return auth_response_for_user(user)


@app.post("/auth/login", response_model=AuthResponse, tags=["auth"])
def login_endpoint(request: LoginRequest):
    """Validate username/password credentials and issue a JWT."""

    user = authenticate_user(request.username, request.password)
    return auth_response_for_user(user)


@app.post(
    "/auth/forgot-password",
    response_model=SimpleStatusResponse,
    tags=["auth"],
)
def forgot_password_endpoint(request: ForgotPasswordRequest):
    """Reset a password after matching the account username and email."""

    user = find_user_by_username(request.username)
    if not user or str(user.get("email", "")).lower() != str(request.email).lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found for that username and email",
        )

    update_user_password(user, request.new_password)
    return SimpleStatusResponse(success=True, message="Password reset.")


@app.post("/auth/logout", response_model=SimpleStatusResponse, tags=["auth"])
def logout_endpoint():
    """Acknowledge logout; JWTs are stateless and cleared by the client."""

    return SimpleStatusResponse(success=True, message="Signed out.")


@app.post("/auth/verify-token", response_model=TokenValidationResponse, tags=["auth"])
def verify_token_endpoint(request: VerifyTokenRequest):
    """Validate a JWT and return its decoded auth context."""

    payload = verify_jwt_token(request.token)
    if not payload:
        return TokenValidationResponse(valid=False)

    expiry_ts = payload.get("exp")
    expiry_dt = datetime.fromtimestamp(expiry_ts) if expiry_ts else None
    role = payload.get("role", "kitten")

    return TokenValidationResponse(
        valid=True,
        user_id=payload.get("sub"),
        username=payload.get("username"),
        email=payload.get("email"),
        role=role,
        expires_at=expiry_dt.isoformat() if expiry_dt else None,
        token_system_enabled=token_system_enabled(role),
        permissions=permissions_for_role(role),
    )


@app.post("/auth/refresh-token", response_model=AuthResponse, tags=["auth"])
def refresh_token_endpoint(request: TokenRefreshRequest):
    """Refresh a valid JWT while preserving the user's role."""

    payload = verify_jwt_token(request.token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    role = payload.get("role", "kitten")
    username = payload.get("username", payload["sub"])
    token, expiry = create_jwt_token(
        payload["sub"],
        payload["email"],
        role,
        username,
    )
    return AuthResponse(
        token=token,
        user_id=payload["sub"],
        username=username,
        email=payload["email"],
        role=role,
        expires_at=expiry.isoformat(),
        token_system_enabled=token_system_enabled(role),
        permissions=permissions_for_role(role),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
