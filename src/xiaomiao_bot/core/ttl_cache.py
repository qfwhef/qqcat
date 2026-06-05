"""Small TTL cache for expensive runtime lookups."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock
from typing import Generic, TypeVar

T = TypeVar("T")


class TimedValueCache(Generic[T]):
    def __init__(self, *, ttl_seconds: float, clock: Callable[[], float] | None = None) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = float(ttl_seconds)
        self.clock = clock or time.monotonic
        self._lock = Lock()
        self._has_value = False
        self._value: T | None = None
        self._expires_at = 0.0

    def get(self, loader: Callable[[], T]) -> T:
        now = self.clock()
        with self._lock:
            if self._has_value and now < self._expires_at:
                return self._value  # type: ignore[return-value]
            value = loader()
            self._value = value
            self._has_value = True
            self._expires_at = now + self.ttl_seconds
            return value

    def clear(self) -> None:
        with self._lock:
            self._has_value = False
            self._value = None
            self._expires_at = 0.0
