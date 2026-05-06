"""Auth Service for CatCh.

This service owns email verification and JWT creation. It only describes the
authenticated user's role; gameplay permissions are enforced by downstream
services.
"""

from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Literal, Optional
import os
import re
import secrets
import smtplib

import jwt
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from pymongo import MongoClient
from pymongo.errors import PyMongoError

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "your-email@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "").replace(" ", "")
AUTH_DEMO_MODE = os.getenv("AUTH_DEMO_MODE", "false").lower() == "true"
MONGO_URL = os.getenv("MONGO_URL", "")
MONGO_DB = os.getenv("MONGO_DB", "fish_likes_cat")

JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,"
    "http://localhost:5175,http://localhost:3000",
)

UserRole = Literal["kitten", "cat"]

# In-memory fallback for local tests and development without Mongo.
verification_codes: dict[str, dict] = {}
mongo_client = (
    MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000) if MONGO_URL else None
)


class SendVerificationEmailRequest(BaseModel):
    """Request body for creating and sending a verification code."""

    email: EmailStr
    username: str = Field(default="", max_length=40)
    role: UserRole = Field(default="kitten")


class VerifyEmailRequest(BaseModel):
    """Request body for validating an email verification code."""

    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    username: str = Field(default="", max_length=40)
    role: UserRole = Field(default="kitten")


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


def verification_collection():
    """Return the verification-code collection when Mongo is configured."""

    if mongo_client is None:
        return None
    return mongo_client[MONGO_DB].email_verification_codes


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


def normalize_username(username: str, email: str) -> str:
    """Create a display-safe username from input or the email prefix."""

    source = username.strip() or email.split("@")[0]
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", source).strip("_")
    return cleaned[:40] or "catch_user"


def find_or_create_user(email: str, role: UserRole, username: str) -> dict:
    """Return a stable user profile and persist it in Mongo when configured."""

    display_name = normalize_username(username, email)
    collection = users_collection()
    if collection is None:
        user_id = f"{role}_{display_name.lower()}"
        return {
            "user_id": user_id,
            "username": display_name,
            "email": email,
            "role": role,
        }

    try:
        existing = collection.find_one({"email": email, "role": role})
        if existing:
            user_id = str(existing.get("user_id") or existing["_id"])
            collection.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "user_id": user_id,
                        "username": display_name,
                        "last_login_at": utc_now(),
                    }
                },
            )
            return {
                "user_id": user_id,
                "username": display_name,
                "email": existing["email"],
                "role": existing["role"],
            }

        now = utc_now()
        user_id = f"{role}_{int(now.timestamp() * 1000)}"
        profile = {
            "_id": user_id,
            "user_id": user_id,
            "username": display_name,
            "email": email,
            "role": role,
            "created_at": now,
            "last_login_at": now,
        }
        collection.insert_one(profile)
        return {
            "user_id": user_id,
            "username": display_name,
            "email": email,
            "role": role,
        }
    except PyMongoError as exc:
        print(f"Mongo user error: {exc}")
        raise mongo_unavailable_error() from exc


def save_verification_code(email: str, payload: dict) -> None:
    """Persist a verification code in Mongo or the local fallback store."""

    collection = verification_collection()
    if collection is None:
        verification_codes[email] = payload
        return

    document = {"_id": email, "email": email, **payload}
    try:
        collection.replace_one({"_id": email}, document, upsert=True)
    except PyMongoError as exc:
        print(f"Mongo verification save error: {exc}")
        raise mongo_unavailable_error() from exc


def get_verification_code(email: str) -> Optional[dict]:
    """Return a verification-code payload from Mongo or local fallback."""

    collection = verification_collection()
    if collection is None:
        return verification_codes.get(email)

    try:
        return collection.find_one({"_id": email})
    except PyMongoError as exc:
        print(f"Mongo verification read error: {exc}")
        raise mongo_unavailable_error() from exc


def delete_verification_code(email: str) -> None:
    """Remove a verification-code payload from Mongo or local fallback."""

    collection = verification_collection()
    if collection is None:
        verification_codes.pop(email, None)
        return

    try:
        collection.delete_one({"_id": email})
    except PyMongoError as exc:
        print(f"Mongo verification delete error: {exc}")
        raise mongo_unavailable_error() from exc


def increment_verification_attempts(email: str, stored: dict) -> None:
    """Track a failed verification attempt."""

    collection = verification_collection()
    if collection is None:
        stored["attempts"] += 1
        return

    try:
        collection.update_one({"_id": email}, {"$inc": {"attempts": 1}})
    except PyMongoError as exc:
        print(f"Mongo verification attempt error: {exc}")
        raise mongo_unavailable_error() from exc


def send_verification_email(
    to_email: str, verification_code: str, role: UserRole
) -> bool:
    """Send a CatCh login code. Returns False when SMTP is not configured."""
    if not SENDER_PASSWORD:
        print("SMTP password is not configured; skipping outbound email.")
        return False

    role_name = "cat teacher" if role == "cat" else "kitten programmer"
    text = (
        f"Welcome to CatCh, {role_name}.\n\n"
        f"Your verification code is: {verification_code}\n\n"
        "This code expires in 10 minutes."
    )
    html = f"""
<html>
  <body>
    <p>Welcome to CatCh, {role_name}.</p>
    <p>Your verification code is <strong>{verification_code}</strong>.</p>
    <p>This code expires in <strong>10 minutes</strong>.</p>
  </body>
</html>
"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "CatCh verification code"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        return True
    except (OSError, smtplib.SMTPException) as exc:
        print(f"SMTP error: {exc}")
        return False


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
    description="CatCh email verification and role-aware JWT generation",
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
def health():
    """Return service health information."""

    return {"status": "ok", "service": "auth-service"}


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


@app.post("/auth/send-verification-email", tags=["auth"])
def send_verification_email_endpoint(request: SendVerificationEmailRequest):
    """Create a short-lived email verification code for the requested role."""

    code = str(secrets.randbelow(1_000_000)).zfill(6)
    expiry = utc_now() + timedelta(minutes=10)
    save_verification_code(
        str(request.email),
        {
            "code": code,
            "role": request.role,
            "username": request.username,
            "created_at": utc_now(),
            "expires_at": expiry,
            "attempts": 0,
        },
    )

    email_sent = send_verification_email(str(request.email), code, request.role)
    response = {
        "success": True,
        "email_sent": email_sent,
        "message": "Verification code created. Configure SMTP to send real email.",
        "role": request.role,
    }
    if not email_sent and AUTH_DEMO_MODE:
        response["development_code"] = code
    return response


@app.post("/auth/verify-email", response_model=AuthResponse, tags=["auth"])
def verify_email_endpoint(request: VerifyEmailRequest):
    """Validate a verification code and issue a role-aware JWT."""

    email = str(request.email)
    stored = get_verification_code(email)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No verification code found for this email",
        )

    if utc_now() > as_utc(stored["expires_at"]):
        delete_verification_code(email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has expired",
        )

    if stored["attempts"] >= 5:
        delete_verification_code(email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts",
        )

    if stored["code"] != request.code:
        increment_verification_attempts(email, stored)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code",
        )

    role: UserRole = stored.get("role", request.role)
    profile = find_or_create_user(
        email,
        role,
        request.username or stored.get("username", ""),
    )
    token, expiry = create_jwt_token(
        profile["user_id"],
        email,
        role,
        profile["username"],
    )
    delete_verification_code(email)

    return AuthResponse(
        token=token,
        user_id=profile["user_id"],
        username=profile["username"],
        email=request.email,
        role=role,
        expires_at=expiry.isoformat(),
        token_system_enabled=token_system_enabled(role),
        permissions=permissions_for_role(role),
    )


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
