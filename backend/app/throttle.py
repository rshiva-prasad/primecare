"""In-memory throttle for /auth/login and /auth/register.

Every GoTrue call leaves from this backend's single IP, so without an app-level limit one client
could spend Supabase's per-IP auth budget for every user. Limits are checked before the gateway
is called, so throttled attempts never reach Supabase.

The counters live in this process only: each uvicorn worker or serverless instance keeps its own,
so the limits are per instance, not global. A shared store (e.g. Redis) would be needed for that.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Hashable

from app.errors import RateLimited

logger = logging.getLogger(__name__)

LOGIN_FAILURE_LIMIT = 5  # failed logins per (client IP, email)...
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60  # ...within 15 minutes; reset by a successful login
ATTEMPT_LIMIT = 20  # login + register attempts per client IP...
ATTEMPT_WINDOW_SECONDS = 5 * 60  # ...within 5 minutes
MAX_TRACKED_KEYS = 10_000  # per window, so memory stays bounded


class SlidingWindow:
    """Counts events per key over the last `window` seconds. Not thread-safe on its own.

    Each key keeps at most `limit` timestamps and at most `max_keys` keys are tracked, so memory
    is bounded by max_keys * limit.
    """

    def __init__(self, limit: int, window: float, *, max_keys: int = MAX_TRACKED_KEYS) -> None:
        self.limit = limit
        self.window = window
        self.max_keys = max_keys
        self._events: dict[Hashable, deque[float]] = {}

    def __len__(self) -> int:
        return len(self._events)

    def _live(self, key: Hashable, now: float) -> deque[float] | None:
        events = self._events.get(key)
        if events is None:
            return None
        cutoff = now - self.window
        while events and events[0] <= cutoff:
            events.popleft()
        if not events:
            del self._events[key]
            return None
        return events

    def is_full(self, key: Hashable, now: float) -> bool:
        events = self._live(key, now)
        return events is not None and len(events) >= self.limit

    def add(self, key: Hashable, now: float) -> None:
        events = self._live(key, now)
        if events is None:
            self._make_room(now)
            events = self._events[key] = deque(maxlen=self.limit)
        events.append(now)

    def clear(self, key: Hashable) -> None:
        self._events.pop(key, None)

    def _make_room(self, now: float) -> None:
        if len(self._events) < self.max_keys:
            return
        for key in list(self._events):  # drop expired keys first...
            self._live(key, now)
        while len(self._events) >= self.max_keys:  # ...then the oldest-inserted ones
            del self._events[next(iter(self._events))]


class AuthThrottle:
    """Per-(IP, email) failed-login limit plus a per-IP cap on login and register attempts."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = MAX_TRACKED_KEYS,
    ) -> None:
        self.enabled = enabled
        self._clock = clock
        # Endpoints are sync and run in FastAPI's threadpool.
        self._lock = threading.Lock()
        self._failures = SlidingWindow(
            LOGIN_FAILURE_LIMIT, LOGIN_FAILURE_WINDOW_SECONDS, max_keys=max_keys
        )
        self._attempts = SlidingWindow(ATTEMPT_LIMIT, ATTEMPT_WINDOW_SECONDS, max_keys=max_keys)

    @staticmethod
    def _account(client_ip: str, email: str) -> tuple[str, str]:
        return client_ip, email.strip().lower()

    def _admit(self, client_ip: str, account: tuple[str, str] | None) -> None:
        if not self.enabled:
            return
        with self._lock:
            now = self._clock()
            if self._attempts.is_full(client_ip, now):
                bucket = "client"
            elif account is not None and self._failures.is_full(account, now):
                bucket = "account"
            else:
                self._attempts.add(client_ip, now)
                return
        # No IP or email in the log: both identify a person.
        logger.info("Auth attempt throttled (%s limit)", bucket)
        raise RateLimited()

    def check_register(self, client_ip: str) -> None:
        """Raise RateLimited, or count this register attempt against the client's cap."""
        self._admit(client_ip, None)

    def check_login(self, client_ip: str, email: str) -> None:
        """Raise RateLimited, or count this login attempt against the client's cap."""
        self._admit(client_ip, self._account(client_ip, email))

    def login_failed(self, client_ip: str, email: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._failures.add(self._account(client_ip, email), self._clock())

    def login_succeeded(self, client_ip: str, email: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._failures.clear(self._account(client_ip, email))
