from __future__ import annotations

import hmac
import time
from collections.abc import Callable

from itsdangerous import BadSignature, TimestampSigner

from backend.errors import InvalidPasswordError, TooManyAttemptsError
from backend.settings import Settings

SESSION_COOKIE = "scraper_ui_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
SESSION_SUBJECT = "owner"
SESSION_SALT = "scraper-ui-session"
MAX_FAILED_ATTEMPTS = 5
FAILURE_WINDOW_SECONDS = 15 * 60.0


class LoginLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures: dict[str, tuple[float, ...]] = {}

    def check(self, client: str) -> None:
        if len(self._read_recent_failures(client)) >= MAX_FAILED_ATTEMPTS:
            raise TooManyAttemptsError()

    def record_failure(self, client: str) -> None:
        recent_failures = (*self._read_recent_failures(client), self._clock())
        self._failures = {**self._failures, client: recent_failures}

    def clear(self, client: str) -> None:
        remaining_failures: dict[str, tuple[float, ...]] = {}
        for failed_client, failure_moments in self._failures.items():
            if failed_client == client:
                continue
            remaining_failures[failed_client] = failure_moments
        self._failures = remaining_failures

    def _read_recent_failures(self, client: str) -> tuple[float, ...]:
        cutoff = self._clock() - FAILURE_WINDOW_SECONDS
        recent_failures: list[float] = []
        for failure_moment in self._failures.get(client, ()):
            if failure_moment > cutoff:
                recent_failures.append(failure_moment)
        return tuple(recent_failures)


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._auth_token = settings.auth_token
        self._signer = TimestampSigner(settings.auth_token, salt=SESSION_SALT)
        self._limiter = LoginLimiter()

    def login(self, password: str, client: str) -> str:
        self._limiter.check(client)
        if not self.is_auth_token(password):
            self._limiter.record_failure(client)
            raise InvalidPasswordError()
        self._limiter.clear(client)
        return self._signer.sign(SESSION_SUBJECT).decode()

    def is_signed_in(self, token: str | None) -> bool:
        if token is None:
            return False
        try:
            self._signer.unsign(token, max_age=SESSION_MAX_AGE_SECONDS)
        except BadSignature:
            return False
        return True

    def is_auth_token(self, token: str | None) -> bool:
        if token is None or not self._auth_token:
            return False
        return hmac.compare_digest(token.encode(), self._auth_token.encode())
