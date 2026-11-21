from __future__ import annotations

import pytest
from argon2 import PasswordHasher
from itsdangerous import TimestampSigner

from backend.errors import InvalidPasswordError, TooManyAttemptsError
from backend.services.auth_service import (
    MAX_FAILED_ATTEMPTS,
    SESSION_SALT,
    SESSION_SUBJECT,
    AuthService,
    LoginLimiter,
)
from backend.settings import Settings

PASSWORD = "correct horse battery"  # pragma: allowlist secret
AUTH_TOKEN = "auth-token-for-tests-1234"


def _service() -> AuthService:
    settings = Settings(
        env="prod",
        password_hash=PasswordHasher().hash(PASSWORD),
        session_secret="s" * 32,
        domain="ui.example.com",
    )
    return AuthService(settings)


def _dev_service() -> AuthService:
    return AuthService(Settings(env="dev", auth_token=AUTH_TOKEN))


def test_auth_token_gives_valid_session_in_dev():
    service = _dev_service()

    assert service.is_signed_in(service.login(AUTH_TOKEN, "1.1.1.1")) is True


@pytest.mark.parametrize("password", ["wrong", f"{AUTH_TOKEN} ", AUTH_TOKEN.upper(), ""])
def test_dev_rejects_anything_but_the_auth_token(password: str):
    with pytest.raises(InvalidPasswordError):
        _dev_service().login(password, "1.1.1.1")


def test_dev_ignores_the_prod_password_hash():
    service = AuthService(
        Settings(
            env="dev",
            auth_token=AUTH_TOKEN,
            password_hash=PasswordHasher().hash(PASSWORD),
        )
    )

    with pytest.raises(InvalidPasswordError):
        service.login(PASSWORD, "1.1.1.1")


def test_dev_session_is_not_signed_with_a_known_secret():
    forged = TimestampSigner("dev", salt=SESSION_SALT).sign(SESSION_SUBJECT).decode()

    assert _dev_service().is_signed_in(forged) is False


def test_dev_failures_block_client():
    service = _dev_service()
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidPasswordError):
            service.login("wrong", "1.1.1.1")

    with pytest.raises(TooManyAttemptsError):
        service.login(AUTH_TOKEN, "1.1.1.1")


def test_right_password_gives_valid_session():
    service = _service()

    token = service.login(PASSWORD, "1.1.1.1")

    assert service.is_signed_in(token) is True


def test_wrong_password_is_rejected():
    with pytest.raises(InvalidPasswordError):
        _service().login("wrong", "1.1.1.1")


def test_tampered_token_is_rejected():
    service = _service()

    assert service.is_signed_in(service.login(PASSWORD, "1.1.1.1") + "x") is False


def test_missing_token_is_rejected():
    assert _service().is_signed_in(None) is False


def test_too_many_failures_block_client():
    service = _service()
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidPasswordError):
            service.login("wrong", "1.1.1.1")

    with pytest.raises(TooManyAttemptsError):
        service.login(PASSWORD, "1.1.1.1")


def test_block_applies_to_one_client_only():
    service = _service()
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(InvalidPasswordError):
            service.login("wrong", "1.1.1.1")

    assert service.is_signed_in(service.login(PASSWORD, "2.2.2.2")) is True


def test_limiter_forgets_old_failures():
    now = [0.0]
    limiter = LoginLimiter(clock=lambda: now[0])
    for _ in range(MAX_FAILED_ATTEMPTS):
        limiter.record_failure("1.1.1.1")

    now[0] = 10_000.0

    limiter.check("1.1.1.1")
