import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: CircuitState
    consecutive_failures: int
    retry_after_seconds: float


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1 or cooldown_seconds <= 0:
            raise ValueError("Circuit breaker limits must be positive")
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._open_until = 0.0

    def acquire(self) -> bool:
        with self._lock:
            if self._state is CircuitState.CLOSED:
                return True
            now = self._clock()
            if self._state is CircuitState.OPEN and now >= self._open_until:
                self._state = CircuitState.HALF_OPEN
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._open_until = 0.0

    def record_failure(self, cooldown_seconds: float | None = None) -> None:
        with self._lock:
            self._consecutive_failures += 1
            should_open = (
                self._state is CircuitState.HALF_OPEN
                or self._consecutive_failures >= self._failure_threshold
            )
            if should_open:
                cooldown = cooldown_seconds or self._cooldown_seconds
                self._state = CircuitState.OPEN
                self._open_until = self._clock() + max(1.0, cooldown)

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            retry_after = (
                max(0.0, self._open_until - self._clock())
                if self._state is CircuitState.OPEN
                else 0.0
            )
            return CircuitSnapshot(
                state=self._state,
                consecutive_failures=self._consecutive_failures,
                retry_after_seconds=retry_after,
            )
