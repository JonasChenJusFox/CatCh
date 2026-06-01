"""Auth Service for CatCh.

This service owns username/password authentication and JWT creation. It only
describes the authenticated user's role; gameplay permissions are enforced by
downstream services.
"""

import base64
import hashlib
import hmac
import smtplib
import socket
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Literal, Optional
import os
import re
import secrets

import jwt
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "")
MONGO_DB = os.getenv("MONGO_DB", "fish_likes_cat")

JWT_SECRET = os.getenv("JWT_SECRET", "your-super-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
PASSWORD_HASH_ITERATIONS = int(os.getenv("PASSWORD_HASH_ITERATIONS", "210000"))
VERIFICATION_CODE_LENGTH = int(os.getenv("VERIFICATION_CODE_LENGTH", "6"))
VERIFICATION_CODE_TTL_MINUTES = int(os.getenv("VERIFICATION_CODE_TTL_MINUTES", "10"))
VERIFICATION_CODE_MAX_ATTEMPTS = int(os.getenv("VERIFICATION_CODE_MAX_ATTEMPTS", "5"))
VERIFICATION_CODE_PEPPER = os.getenv(
    "VERIFICATION_CODE_PEPPER",
    "change-me-for-local-dev",
)
VERIFICATION_CODE_DELIVERY = os.getenv("VERIFICATION_CODE_DELIVERY", "smtp").lower()
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "CatCh")
SMTP_REPLY_TO = os.getenv("SMTP_REPLY_TO", SMTP_FROM_EMAIL)
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
SMTP_TIMEOUT_SECONDS = int(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,"
    "http://localhost:5175,http://localhost:3000",
)
BUILD_VERSION = os.getenv("BUILD_VERSION", "auth-password-v1")

UserRole = Literal["kitten", "cat"]

# In-memory fallback for local tests and development without Mongo.
local_users: dict[str, dict] = {}
local_verification_codes: dict[str, dict] = {}
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


class VerificationCodeRequest(BaseModel):
    """Request body for sending an email verification code."""

    email: EmailStr
    role: UserRole = Field(default="kitten")


class VerificationCodeLoginRequest(BaseModel):
    """Request body for logging in with an emailed verification code."""

    email: EmailStr
    code: str = Field(min_length=4, max_length=12)
    role: UserRole = Field(default="kitten")


class ForgotPasswordRequest(BaseModel):
    """Request body for resetting a password."""

    username: str = Field(min_length=2, max_length=40)
    email: EmailStr
    new_password: str = Field(min_length=8, max_length=128)


class SimpleStatusResponse(BaseModel):
    """Generic success response."""

    success: bool
    message: str


class VerificationCodeStatusResponse(SimpleStatusResponse):
    """Response for verification-code requests.

    debug_code is only returned when local console delivery is explicitly enabled.
    """

    debug_code: Optional[str] = None


class SmtpDiagnosticsResponse(BaseModel):
    """SMTP configuration and connectivity diagnostics without secrets."""

    delivery_mode: str
    configured: bool
    host: str
    port: int
    username: str
    from_email: str
    use_tls: bool
    dns_ok: bool
    tcp_ok: bool
    tls_ok: bool
    auth_ok: bool
    error_stage: Optional[str] = None
    error: Optional[str] = None


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


def verification_codes_collection():
    """Return the verification-code collection when Mongo is configured."""

    if mongo_client is None:
        return None
    return mongo_client[MONGO_DB].verification_codes


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


def email_key(email: str) -> str:
    """Return the case-insensitive lookup key for an email address."""

    return email.strip().lower()


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


def hash_verification_code(email: str, code: str, salt: bytes) -> str:
    """Return a keyed hash for an email verification code."""

    material = f"{email_key(email)}:{code}:{VERIFICATION_CODE_PEPPER}".encode("utf-8")
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        material,
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return base64.b64encode(digest).decode("ascii")


def generate_verification_code() -> str:
    """Generate a numeric verification code."""

    maximum = 10**VERIFICATION_CODE_LENGTH
    return f"{secrets.randbelow(maximum):0{VERIFICATION_CODE_LENGTH}d}"


def send_verification_email(email: str, code: str) -> None:
    """Send a verification code with the configured SMTP account."""

    if VERIFICATION_CODE_DELIVERY == "console":
        print(f"CatCh local verification code for {email}: {code}")
        return

    if not SMTP_HOST or not SMTP_FROM_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP email delivery is not configured",
        )

    message = EmailMessage()
    message["Subject"] = "Your CatCh verification code"
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = email
    if SMTP_REPLY_TO:
        message["Reply-To"] = SMTP_REPLY_TO
    message.set_content(
        "\n".join(
            [
                f"Your CatCh verification code is {code}.",
                f"It expires in {VERIFICATION_CODE_TTL_MINUTES} minutes.",
                "If you did not request this code, you can ignore this email.",
            ]
        )
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            if SMTP_USE_TLS:
                smtp.starttls()
            if SMTP_USERNAME or SMTP_PASSWORD:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        print(f"SMTP authentication error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="SMTP username or app password was rejected",
        ) from exc
    except smtplib.SMTPException as exc:
        print(f"SMTP verification email error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Verification email could not be sent",
        ) from exc
    except OSError as exc:
        print(f"SMTP connection error: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Verification email service is unavailable",
        ) from exc


def run_smtp_diagnostics() -> dict:
    """Check SMTP setup without sending a message or exposing secrets."""

    result = {
        "delivery_mode": VERIFICATION_CODE_DELIVERY,
        "configured": bool(SMTP_HOST and SMTP_FROM_EMAIL),
        "host": SMTP_HOST,
        "port": SMTP_PORT,
        "username": SMTP_USERNAME,
        "from_email": SMTP_FROM_EMAIL,
        "use_tls": SMTP_USE_TLS,
        "dns_ok": False,
        "tcp_ok": False,
        "tls_ok": False,
        "auth_ok": False,
        "error_stage": None,
        "error": None,
    }

    if VERIFICATION_CODE_DELIVERY == "console":
        result.update(
            {
                "configured": True,
                "dns_ok": True,
                "tcp_ok": True,
                "tls_ok": True,
                "auth_ok": True,
            }
        )
        return result

    if not result["configured"]:
        result["error_stage"] = "configuration"
        result["error"] = "SMTP_HOST and SMTP_FROM_EMAIL are required"
        return result

    try:
        socket.getaddrinfo(SMTP_HOST, SMTP_PORT, type=socket.SOCK_STREAM)
        result["dns_ok"] = True

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            result["tcp_ok"] = True
            if SMTP_USE_TLS:
                smtp.starttls()
            result["tls_ok"] = True
            if SMTP_USERNAME or SMTP_PASSWORD:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            result["auth_ok"] = True
    except socket.gaierror as exc:
        result["error_stage"] = "dns"
        result["error"] = str(exc)
    except smtplib.SMTPAuthenticationError as exc:
        result["error_stage"] = "auth"
        result["error"] = str(exc)
    except smtplib.SMTPException as exc:
        result["error_stage"] = "smtp"
        result["error"] = str(exc)
    except OSError as exc:
        result["error_stage"] = "tcp"
        result["error"] = str(exc)

    return result


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


def find_user_by_email(email: str) -> Optional[dict]:
    """Return a user profile by email from Mongo or local storage."""

    key = email_key(email)
    collection = users_collection()
    if collection is None:
        return next(
            (
                user
                for user in local_users.values()
                if email_key(str(user.get("email", ""))) == key
            ),
            None,
        )

    try:
        return collection.find_one({"email_key": key})
    except PyMongoError as exc:
        print(f"Mongo email lookup error: {exc}")
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
        "email_key": email_key(email),
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


def unique_username_from_email(email: str) -> str:
    """Create a unique username candidate from an email local part."""

    local_part = email.split("@", 1)[0]
    if len(re.sub(r"[^A-Za-z0-9_-]+", "_", local_part).strip("_")) < 2:
        local_part = f"{local_part}_user"
    base = normalize_username(local_part)
    candidate = base
    suffix = 1
    while find_user_by_username(candidate):
        suffix += 1
        candidate = f"{base}_{suffix}"
    return candidate


def create_passwordless_user(email: str, role: UserRole) -> dict:
    """Create a user profile for verification-code login."""

    username = unique_username_from_email(email)
    now = utc_now()
    user_id = f"{role}_{int(now.timestamp() * 1000)}"
    profile = {
        "_id": user_id,
        "user_id": user_id,
        "username": username,
        "username_key": username.lower(),
        "email": email,
        "email_key": email_key(email),
        "role": role,
        "password_hash": "",
        "created_at": now,
        "last_login_at": now,
        "auth_method": "email_code",
    }

    collection = users_collection()
    if collection is None:
        local_users[profile["username_key"]] = profile
        return profile

    try:
        collection.insert_one(profile)
        return profile
    except PyMongoError as exc:
        print(f"Mongo passwordless user create error: {exc}")
        raise mongo_unavailable_error() from exc


def store_verification_code(email: str, code: str) -> None:
    """Hash and persist a verification code until it expires."""

    now = utc_now()
    salt = secrets.token_bytes(16)
    record = {
        "email_key": email_key(email),
        "code_hash": hash_verification_code(email, code, salt),
        "salt": base64.b64encode(salt).decode("ascii"),
        "expires_at": now + timedelta(minutes=VERIFICATION_CODE_TTL_MINUTES),
        "attempts": 0,
        "max_attempts": VERIFICATION_CODE_MAX_ATTEMPTS,
        "created_at": now,
    }

    collection = verification_codes_collection()
    if collection is None:
        local_verification_codes[record["email_key"]] = record
        return

    try:
        collection.update_one(
            {"email_key": record["email_key"]},
            {"$set": record},
            upsert=True,
        )
    except PyMongoError as exc:
        print(f"Mongo verification-code store error: {exc}")
        raise mongo_unavailable_error() from exc


def get_verification_code_record(email: str) -> Optional[dict]:
    """Return a stored verification code record."""

    key = email_key(email)
    collection = verification_codes_collection()
    if collection is None:
        return local_verification_codes.get(key)

    try:
        return collection.find_one({"email_key": key})
    except PyMongoError as exc:
        print(f"Mongo verification-code lookup error: {exc}")
        raise mongo_unavailable_error() from exc


def increment_verification_attempts(email: str, attempts: int) -> None:
    """Persist the latest failed verification attempt count."""

    key = email_key(email)
    collection = verification_codes_collection()
    if collection is None:
        if key in local_verification_codes:
            local_verification_codes[key]["attempts"] = attempts
        return

    try:
        collection.update_one({"email_key": key}, {"$set": {"attempts": attempts}})
    except PyMongoError as exc:
        print(f"Mongo verification-code attempts error: {exc}")
        raise mongo_unavailable_error() from exc


def delete_verification_code(email: str) -> None:
    """Remove a verification code after success or expiry."""

    key = email_key(email)
    collection = verification_codes_collection()
    if collection is None:
        local_verification_codes.pop(key, None)
        return

    try:
        collection.delete_one({"email_key": key})
    except PyMongoError as exc:
        print(f"Mongo verification-code delete error: {exc}")
        raise mongo_unavailable_error() from exc


def verify_email_code(email: str, code: str) -> None:
    """Validate a code against the stored hash, expiry, and attempt limit."""

    record = get_verification_code_record(email)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code",
        )

    if as_utc(record["expires_at"]) < utc_now():
        delete_verification_code(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code",
        )

    attempts = int(record.get("attempts", 0)) + 1
    if attempts > int(record.get("max_attempts", VERIFICATION_CODE_MAX_ATTEMPTS)):
        delete_verification_code(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Too many invalid verification code attempts",
        )

    salt = base64.b64decode(record["salt"].encode("ascii"))
    actual = hash_verification_code(email, code, salt)
    if not hmac.compare_digest(actual, record["code_hash"]):
        increment_verification_attempts(email, attempts)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired verification code",
        )

    delete_verification_code(email)


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


@app.get(
    "/auth/smtp/diagnostics",
    response_model=SmtpDiagnosticsResponse,
    tags=["auth"],
)
def smtp_diagnostics_endpoint():
    """Return SMTP setup diagnostics without exposing SMTP_PASSWORD."""

    return SmtpDiagnosticsResponse(**run_smtp_diagnostics())


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
    "/auth/verification-code/request",
    response_model=VerificationCodeStatusResponse,
    tags=["auth"],
)
def request_verification_code_endpoint(request: VerificationCodeRequest):
    """Generate, store, and email a verification code."""

    code = generate_verification_code()
    store_verification_code(str(request.email), code)
    try:
        send_verification_email(str(request.email), code)
    except HTTPException:
        delete_verification_code(str(request.email))
        raise

    debug_code = code if VERIFICATION_CODE_DELIVERY == "console" else None
    return VerificationCodeStatusResponse(
        success=True,
        message="Verification code sent.",
        debug_code=debug_code,
    )


@app.post(
    "/auth/verification-code/login",
    response_model=AuthResponse,
    tags=["auth"],
)
def verification_code_login_endpoint(request: VerificationCodeLoginRequest):
    """Validate an emailed code and issue a role-aware JWT."""

    email = str(request.email)
    verify_email_code(email, request.code.strip())
    user = find_user_by_email(email)
    if not user:
        user = create_passwordless_user(email, request.role)
    update_user_login(user)
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
