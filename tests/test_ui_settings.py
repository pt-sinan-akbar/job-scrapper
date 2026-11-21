from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.settings import Settings

STRONG_SECRET = "s" * 32
DOMAIN = "ui.example.com"
FAKE_HASH = "hash"  # pragma: allowlist secret
SHORT_SECRET = "short"  # pragma: allowlist secret
AUTH_TOKEN = "auth-token-for-tests-1234"


def test_env_is_required(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("UI_ENV", raising=False)

    with pytest.raises(ValidationError, match="env"):
        Settings()


def test_host_defaults_to_loopback():
    assert Settings(env="dev", auth_token=AUTH_TOKEN).host == "127.0.0.1"


def test_dev_allows_only_local_hosts():
    assert Settings(env="dev", auth_token=AUTH_TOKEN).allowed_hosts == (
        "localhost",
        "127.0.0.1",
    )


def test_prod_allows_its_domain():
    settings = Settings(
        env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET, domain=DOMAIN
    )

    assert settings.allowed_hosts == ("localhost", "127.0.0.1", DOMAIN)


def test_prod_refuses_to_start_without_domain():
    with pytest.raises(ValidationError, match="UI_DOMAIN"):
        Settings(env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET)


def test_dev_needs_only_the_auth_token():
    settings = Settings(env="dev", auth_token=AUTH_TOKEN)

    assert settings.auth_token == AUTH_TOKEN
    assert settings.cookie_secure is False


def test_dev_refuses_to_start_without_auth_token(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)

    with pytest.raises(ValidationError, match="AUTH_TOKEN"):
        Settings(env="dev")


def test_refuses_a_short_auth_token():
    with pytest.raises(ValidationError, match="AUTH_TOKEN must have at least 16"):
        Settings(env="dev", auth_token="k" * 15)


def test_prod_keeps_an_optional_auth_token():
    settings = Settings(
        env="prod",
        password_hash=FAKE_HASH,
        session_secret=STRONG_SECRET,
        domain=DOMAIN,
        auth_token="t" * 16,
    )

    assert settings.auth_token == "t" * 16


def test_prod_refuses_a_short_auth_token():
    with pytest.raises(ValidationError, match="AUTH_TOKEN must have at least 16"):
        Settings(
            env="prod",
            password_hash=FAKE_HASH,
            session_secret=STRONG_SECRET,
            domain=DOMAIN,
            auth_token="t" * 15,
        )


def test_auth_token_is_read_from_the_auth_token_variable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AUTH_TOKEN", "from-env-token-1234")

    assert Settings(env="dev").auth_token == "from-env-token-1234"


def test_prod_needs_no_auth_token():
    settings = Settings(
        env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET, domain=DOMAIN
    )

    assert settings.auth_token == ""


def test_prod_refuses_to_start_without_password_hash():
    with pytest.raises(ValidationError, match="UI_PASSWORD_HASH"):
        Settings(env="prod", session_secret=STRONG_SECRET, domain=DOMAIN)


def test_prod_refuses_short_session_secret():
    with pytest.raises(ValidationError, match="UI_SESSION_SECRET"):
        Settings(env="prod", password_hash=FAKE_HASH, session_secret=SHORT_SECRET, domain=DOMAIN)


def test_prod_turns_on_login():
    settings = Settings(
        env="prod", password_hash=FAKE_HASH, session_secret=STRONG_SECRET, domain=DOMAIN
    )

    assert settings.cookie_secure is True
