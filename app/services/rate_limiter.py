"""Rate limiter interface and implementations for upstream throttling."""

from abc import ABC, abstractmethod
import asyncio
import time
from typing import Optional


class BaseRateLimiter(ABC):
    """Abstract interface for rate limiting upstream requests."""

    @abstractmethod
    async def acquire(self):
        """Acquire permission to execute a request, sleeping if rate limit reached."""


class TokenBucketRateLimiter(BaseRateLimiter):
    """Token bucket rate limiter providing smooth request rates."""

    def __init__(self, rate_limit_rps: float = 25.0, burst_capacity: Optional[int] = None):
        self.rate_limit_rps = max(1.0, float(rate_limit_rps))
        self.capacity = float(burst_capacity or max(10, int(self.rate_limit_rps)))
        self.tokens = self.capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_refill
                self.tokens = min(self.capacity, self.tokens + (elapsed * self.rate_limit_rps))
                self.last_refill = now

                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return

                # Calculate sleep duration until next token is available
                needed = 1.0 - self.tokens
                sleep_time = needed / self.rate_limit_rps
                await asyncio.sleep(sleep_time)


class NoOpRateLimiter(BaseRateLimiter):
    """No-op rate limiter used when rate limiting is disabled."""

    async def acquire(self):
        return
