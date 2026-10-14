import logging
import threading

import pytest

from app.errors import RateLimited
from app.throttle import (
    ATTEMPT_LIMIT,
    ATTEMPT_WINDOW_SECONDS,
    LOGIN_FAILURE_LIMIT,
    LOGIN_FAILURE_WINDOW_SECONDS,
    AuthThrottle,
    SlidingWindow,
)

IP = "192.0.2.1"
EMAIL = "pat@example.com"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limits_match_the_contract() -> None:
    assert (LOGIN_FAILURE_LIMIT, LOGIN_FAILURE_WINDOW_SECONDS) == (5, 15 * 60)
    assert (ATTEMPT_LIMIT, ATTEMPT_WINDOW_SECONDS) == (20, 5 * 60)


def test_failed_logins_expire_after_the_window() -> None:
    clock = Clock()
    throttle = AuthThrottle(clock=clock)
    for _ in range(LOGIN_FAILURE_LIMIT):
        throttle.check_login(IP, EMAIL)
        throttle.login_failed(IP, EMAIL)
    with pytest.raises(RateLimited):
        throttle.check_login(IP, " PAT@Example.COM ")  # same account after normalisation
    clock.now += LOGIN_FAILURE_WINDOW_SECONDS - 1
    with pytest.raises(RateLimited):
        throttle.check_login(IP, EMAIL)
    clock.now += 1
    throttle.check_login(IP, EMAIL)


def test_failures_slide_one_at_a_time() -> None:
    clock = Clock()
    throttle = AuthThrottle(clock=clock)
    for _ in range(LOGIN_FAILURE_LIMIT):
        throttle.login_failed(IP, EMAIL)
        clock.now += 60
    # Exactly 15 minutes after the first failure only that one has expired; the rest count.
    clock.now = 1000.0 + LOGIN_FAILURE_WINDOW_SECONDS
    throttle.check_login(IP, EMAIL)
    throttle.login_failed(IP, EMAIL)
    with pytest.raises(RateLimited):
        throttle.check_login(IP, EMAIL)


def test_success_resets_failures() -> None:
    throttle = AuthThrottle(clock=Clock())
    for _ in range(LOGIN_FAILURE_LIMIT):
        throttle.login_failed(IP, EMAIL)
    throttle.login_succeeded(IP, EMAIL.upper())
    throttle.check_login(IP, EMAIL)


def test_client_cap_counts_logins_and_registers_and_expires() -> None:
    clock = Clock()
    throttle = AuthThrottle(clock=clock)
    for n in range(ATTEMPT_LIMIT):
        if n % 2:
            throttle.check_register(IP)
        else:
            throttle.check_login(IP, f"user{n}@example.com")
    with pytest.raises(RateLimited):
        throttle.check_register(IP)
    with pytest.raises(RateLimited):
        throttle.check_login(IP, "someone@example.com")
    throttle.check_register("192.0.2.2")  # other clients are unaffected
    clock.now += ATTEMPT_WINDOW_SECONDS
    throttle.check_register(IP)


def test_throttled_attempts_are_not_counted() -> None:
    clock = Clock()
    throttle = AuthThrottle(clock=clock)
    for _ in range(LOGIN_FAILURE_LIMIT):
        throttle.login_failed(IP, EMAIL)
    for _ in range(ATTEMPT_LIMIT * 2):
        with pytest.raises(RateLimited):
            throttle.check_login(IP, EMAIL)
    # Blocked account attempts did not use up the client's cap.
    for n in range(ATTEMPT_LIMIT):
        throttle.check_login(IP, f"user{n}@example.com")


def test_disabled_throttle_never_blocks() -> None:
    throttle = AuthThrottle(enabled=False)
    for _ in range(ATTEMPT_LIMIT * 2):
        throttle.check_login(IP, EMAIL)
        throttle.login_failed(IP, EMAIL)
        throttle.check_register(IP)
    throttle.login_succeeded(IP, EMAIL)


def test_concurrent_attempts_admit_exactly_the_cap() -> None:
    throttle = AuthThrottle()
    admitted: list[int] = []
    start = threading.Barrier(ATTEMPT_LIMIT * 3)

    def attempt() -> None:
        start.wait()
        try:
            throttle.check_register(IP)
        except RateLimited:
            return
        admitted.append(1)

    threads = [threading.Thread(target=attempt) for _ in range(ATTEMPT_LIMIT * 3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(admitted) == ATTEMPT_LIMIT


def test_throttle_log_has_no_ip_or_email(caplog: pytest.LogCaptureFixture) -> None:
    throttle = AuthThrottle()
    for _ in range(LOGIN_FAILURE_LIMIT):
        throttle.login_failed(IP, EMAIL)
    with caplog.at_level(logging.INFO), pytest.raises(RateLimited):
        throttle.check_login(IP, EMAIL)
    assert "account limit" in caplog.text
    assert IP not in caplog.text
    assert EMAIL not in caplog.text


def test_sliding_window_memory_is_bounded() -> None:
    window = SlidingWindow(limit=3, window=10, max_keys=3)
    for _ in range(10):
        window.add("a", 0)
    assert window._events["a"].maxlen == 3
    assert len(window._events["a"]) == 3
    window.add("b", 0)
    window.add("c", 5)
    window.add("d", 11)  # full: "a" and "b" have expired, so only they are dropped
    assert set(window._events) == {"c", "d"}
    window.add("e", 11)
    window.add("f", 12)  # full of live keys: the oldest-inserted ("c") is evicted
    assert set(window._events) == {"d", "e", "f"}
    assert len(window) == 3


def test_sliding_window_prunes_and_clears() -> None:
    window = SlidingWindow(limit=2, window=10)
    assert window.is_full("x", 0) is False
    window.add("x", 0)
    window.add("x", 1)
    assert window.is_full("x", 9) is True
    assert window.is_full("x", 10.5) is False  # first event expired
    assert window.is_full("x", 20) is False
    assert "x" not in window._events  # fully expired keys are dropped
    window.add("y", 0)
    window.clear("y")
    window.clear("missing")
    assert len(window) == 0
