import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from app.exceptions import TooManyRequestsError


class AbstractRateLimiter(ABC):
    @abstractmethod
    async def check(self, key: str, limit: int, window_seconds: int, action: str) -> None:
        """Raise TooManyRequestsError if the key has exceeded limit within window_seconds."""


class NoOpRateLimiter(AbstractRateLimiter):
    """Always allows — used in tests and when rate limiting is disabled."""

    async def check(self, key: str, limit: int, window_seconds: int, action: str) -> None:
        pass


class InMemoryRateLimiter(AbstractRateLimiter):
    """
    Simple in-memory sliding-window rate limiter.
    NOT suitable for multi-process production deployments.
    Use RedisRateLimiter in production.
    """

    def __init__(self) -> None:
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def check(self, key: str, limit: int, window_seconds: int, action: str) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        hits = self._windows[key]
        # Prune expired entries
        self._windows[key] = [t for t in hits if t > cutoff]
        if len(self._windows[key]) >= limit:
            from app.infrastructure.logging.security_log import log_rate_limit_triggered
            log_rate_limit_triggered(limit_name=action)
            raise TooManyRequestsError(
                f"Too many {action} requests. Try again later."
            )
        self._windows[key].append(now)


_noop_limiter = NoOpRateLimiter()
_default_limiter: AbstractRateLimiter = _noop_limiter


def get_rate_limiter() -> AbstractRateLimiter:
    """FastAPI dependency — returns the process-wide rate limiter instance."""
    return _default_limiter


def configure_rate_limiter(limiter: AbstractRateLimiter) -> None:
    """Called at startup to swap in the real limiter."""
    global _default_limiter
    _default_limiter = limiter
