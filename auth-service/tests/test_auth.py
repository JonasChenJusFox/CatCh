"""Tests for the CatCh auth-service FastAPI app."""

import importlib.util
import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["MONGO_URL"] = ""

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
spec = importlib.util.spec_from_file_location("auth_service_main", MODULE_PATH)
auth_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth_main)

client = TestClient(auth_main.app)


def setup_function():
    """Reset in-memory users before each test."""

    auth_main.local_users.clear()
    auth_main.local_verification_codes.clear()


def signup_payload(**overrides):
    """Return a valid signup payload with optional overrides."""

    payload = {
        "username": "Tiny Tuna",
        "password": "correct-horse-123",
        "email": "kitten@example.com",
        "role": "kitten",
    }
    payload.update(overrides)
    return payload


def test_health():
    """Health endpoint reports auth-service status."""

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "auth-service"


def test_roles_describe_cat_and_kitten_permissions():
    """Role metadata separates cats from the token economy."""

    response = client.get("/auth/roles")
    assert response.status_code == 200
    roles = response.json()["roles"]
    assert roles["kitten"]["token_system_enabled"] is True
    assert roles["cat"]["token_system_enabled"] is False


def test_signup_creates_kitten_token_and_hashed_password():
    """A new username/password account receives a role-aware JWT."""

    response = client.post("/auth/signup", json=signup_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "Tiny_Tuna"
    assert body["role"] == "kitten"
    assert body["token_system_enabled"] is True

    stored = auth_main.local_users["tiny_tuna"]
    assert stored["password_hash"] != "correct-horse-123"
    assert auth_main.verify_password("correct-horse-123", stored["password_hash"])

    token_response = client.post("/auth/verify-token", json={"token": body["token"]})
    assert token_response.status_code == 200
    assert token_response.json()["valid"] is True


def test_two_character_username_can_sign_up():
    """Two-character usernames are accepted."""

    response = client.post(
        "/auth/signup",
        json=signup_payload(username="JJ", email="jj@example.com"),
    )
    assert response.status_code == 200
    assert response.json()["username"] == "JJ"


def test_one_character_username_is_rejected():
    """One-character usernames return a validation error."""

    response = client.post(
        "/auth/signup",
        json=signup_payload(username="J", email="j@example.com"),
    )
    assert response.status_code == 422
    detail = response.json()["detail"][0]
    assert detail["loc"] == ["body", "username"]
    assert detail["ctx"]["min_length"] == 2


def test_duplicate_username_is_rejected_case_insensitively():
    """Usernames are unique regardless of case."""

    client.post("/auth/signup", json=signup_payload(username="Pond Cat"))
    response = client.post(
        "/auth/signup",
        json=signup_payload(
            username="pond cat",
            email="another@example.com",
            password="another-password-123",
        ),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Username is already taken"


def test_login_accepts_valid_credentials():
    """A registered account can sign in with username and password."""

    client.post(
        "/auth/signup",
        json=signup_payload(
            username="Professor Cat",
            password="lesson-plan-123",
            email="teacher@example.com",
            role="cat",
        ),
    )

    response = client.post(
        "/auth/login",
        json={"username": "professor cat", "password": "lesson-plan-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "Professor_Cat"
    assert body["role"] == "cat"
    assert body["token_system_enabled"] is False


def test_login_rejects_wrong_password():
    """Invalid passwords return an auth error."""

    client.post("/auth/signup", json=signup_payload())
    response = client.post(
        "/auth/login",
        json={"username": "Tiny Tuna", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"


def test_request_verification_code_hashes_code_and_sends_email(monkeypatch):
    """Requesting a code stores only a hash and sends the plain code by email."""

    sent = {}

    def fake_send(email, code):
        sent["email"] = email
        sent["code"] = code

    monkeypatch.setattr(auth_main, "send_verification_email", fake_send)

    response = client.post(
        "/auth/verification-code/request",
        json={"email": "kitten@example.com", "role": "kitten"},
    )

    assert response.status_code == 200
    assert sent["email"] == "kitten@example.com"
    record = auth_main.local_verification_codes["kitten@example.com"]
    assert record["code_hash"] != sent["code"]
    assert record["attempts"] == 0


def test_request_verification_code_console_delivery_returns_debug_code(monkeypatch):
    """Local demo mode returns the code without requiring SMTP network access."""

    monkeypatch.setattr(auth_main, "VERIFICATION_CODE_DELIVERY", "console")

    response = client.post(
        "/auth/verification-code/request",
        json={"email": "kitten@example.com", "role": "kitten"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["debug_code"]
    record = auth_main.local_verification_codes["kitten@example.com"]
    assert record["code_hash"] != body["debug_code"]


def test_request_verification_code_deletes_record_when_send_fails(monkeypatch):
    """A failed SMTP send should not leave an unusable verification code."""

    def fail_send(_email, _code):
        raise auth_main.HTTPException(
            status_code=502,
            detail="Verification email service is unavailable",
        )

    monkeypatch.setattr(auth_main, "send_verification_email", fail_send)

    response = client.post(
        "/auth/verification-code/request",
        json={"email": "kitten@example.com", "role": "kitten"},
    )

    assert response.status_code == 502
    assert "kitten@example.com" not in auth_main.local_verification_codes


def test_send_verification_email_reports_authentication_failure(monkeypatch):
    """Rejected SMTP credentials should produce a clear operator-facing error."""

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, *_args):
            raise auth_main.smtplib.SMTPAuthenticationError(
                535,
                b"Username and Password not accepted",
            )

    monkeypatch.setattr(auth_main, "VERIFICATION_CODE_DELIVERY", "smtp")
    monkeypatch.setattr(auth_main, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(auth_main, "SMTP_FROM_EMAIL", "fishlikecat@gmail.com")
    monkeypatch.setattr(auth_main.smtplib, "SMTP", FakeSMTP)

    try:
        auth_main.send_verification_email("kitten@example.com", "123456")
    except auth_main.HTTPException as exc:
        assert exc.status_code == 502
        assert exc.detail == "SMTP username or app password was rejected"
    else:
        raise AssertionError("Expected SMTP authentication failure")


def test_smtp_diagnostics_reports_console_mode(monkeypatch):
    """Console mode should be reported as locally usable."""

    monkeypatch.setattr(auth_main, "VERIFICATION_CODE_DELIVERY", "console")

    response = client.get("/auth/smtp/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_mode"] == "console"
    assert body["auth_ok"] is True


def test_smtp_diagnostics_reports_tcp_failure(monkeypatch):
    """Network failures should identify the TCP stage."""

    def fail_smtp(*_args, **_kwargs):
        raise OSError("Network is unreachable")

    monkeypatch.setattr(auth_main, "VERIFICATION_CODE_DELIVERY", "smtp")
    monkeypatch.setattr(auth_main, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(auth_main, "SMTP_FROM_EMAIL", "fishlikescat@gmail.com")
    monkeypatch.setattr(auth_main.smtplib, "SMTP", fail_smtp)

    response = client.get("/auth/smtp/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["dns_ok"] is True
    assert body["tcp_ok"] is False
    assert body["error_stage"] == "tcp"
    assert "Network is unreachable" in body["error"]


def test_smtp_diagnostics_reports_auth_failure(monkeypatch):
    """Rejected SMTP credentials should be visible in diagnostics."""

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def starttls(self):
            return None

        def login(self, *_args):
            raise auth_main.smtplib.SMTPAuthenticationError(
                535,
                b"Username and Password not accepted",
            )

    monkeypatch.setattr(auth_main, "VERIFICATION_CODE_DELIVERY", "smtp")
    monkeypatch.setattr(auth_main, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(auth_main, "SMTP_FROM_EMAIL", "fishlikescat@gmail.com")
    monkeypatch.setattr(auth_main.smtplib, "SMTP", FakeSMTP)

    response = client.get("/auth/smtp/diagnostics")

    assert response.status_code == 200
    body = response.json()
    assert body["tcp_ok"] is True
    assert body["tls_ok"] is True
    assert body["auth_ok"] is False
    assert body["error_stage"] == "auth"


def test_verification_code_login_issues_role_aware_jwt(monkeypatch):
    """A valid emailed code creates a passwordless user and returns a JWT."""

    sent = {}

    def fake_send(email, code):
        sent["email"] = email
        sent["code"] = code

    monkeypatch.setattr(auth_main, "send_verification_email", fake_send)
    client.post(
        "/auth/verification-code/request",
        json={"email": "teacher@example.com", "role": "cat"},
    )

    response = client.post(
        "/auth/verification-code/login",
        json={"email": "teacher@example.com", "code": sent["code"], "role": "cat"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "teacher@example.com"
    assert body["role"] == "cat"
    assert body["token_system_enabled"] is False
    assert "teacher@example.com" not in auth_main.local_verification_codes


def test_verification_code_login_rejects_wrong_code(monkeypatch):
    """Invalid codes do not issue tokens and increment attempt counts."""

    monkeypatch.setattr(
        auth_main, "send_verification_email", lambda _email, _code: None
    )
    client.post(
        "/auth/verification-code/request",
        json={"email": "kitten@example.com", "role": "kitten"},
    )

    response = client.post(
        "/auth/verification-code/login",
        json={"email": "kitten@example.com", "code": "000000", "role": "kitten"},
    )

    assert response.status_code == 401
    assert auth_main.local_verification_codes["kitten@example.com"]["attempts"] == 1


def test_forgot_password_resets_matching_account():
    """Forgot-password reset changes the password when username and email match."""

    client.post("/auth/signup", json=signup_payload())
    reset_response = client.post(
        "/auth/forgot-password",
        json={
            "username": "Tiny Tuna",
            "email": "kitten@example.com",
            "new_password": "new-correct-horse-123",
        },
    )
    assert reset_response.status_code == 200
    assert reset_response.json()["success"] is True

    old_login = client.post(
        "/auth/login",
        json={"username": "Tiny Tuna", "password": "correct-horse-123"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={"username": "Tiny Tuna", "password": "new-correct-horse-123"},
    )
    assert new_login.status_code == 200


def test_forgot_password_rejects_email_mismatch():
    """Password reset requires both the username and account email."""

    client.post("/auth/signup", json=signup_payload())
    response = client.post(
        "/auth/forgot-password",
        json={
            "username": "Tiny Tuna",
            "email": "wrong@example.com",
            "new_password": "new-correct-horse-123",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "No account found for that username and email"


def test_logout_acknowledges_client_signout():
    """Logout returns success for the client-side session clear."""

    response = client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_refresh_token_preserves_role():
    """Refreshing a valid token keeps role and permissions."""

    auth_response = client.post(
        "/auth/signup",
        json=signup_payload(
            username="Pond Cat",
            password="lesson-plan-123",
            email="teacher@example.com",
            role="cat",
        ),
    )

    refresh_response = client.post(
        "/auth/refresh-token",
        json={"token": auth_response.json()["token"]},
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["role"] == "cat"
    assert refresh_response.json()["token_system_enabled"] is False


def test_invalid_tokens_are_rejected():
    """Invalid JWTs fail validation and refresh."""

    verify_response = client.post("/auth/verify-token", json={"token": "not-a-token"})
    assert verify_response.status_code == 200
    assert verify_response.json()["valid"] is False

    refresh_response = client.post("/auth/refresh-token", json={"token": "not-a-token"})
    assert refresh_response.status_code == 401
