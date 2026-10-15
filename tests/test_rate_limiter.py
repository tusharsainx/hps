"""Unit tests for the TokenBucketRateLimiter."""

import pytest
import time
from app.services.rate_limiter import TokenBucketRateLimiter


@pytest.mark.asyncio
async def test_token_bucket_rate_limiter():
    # 10 tokens per second, capacity 2
    limiter = TokenBucketRateLimiter(rate_limit_rps=20.0, burst_capacity=2)

    start = time.monotonic()
    # First 2 acquire immediately from burst
    await limiter.acquire()
    await limiter.acquire()
    burst_elapsed = time.monotonic() - start
    assert burst_elapsed < 0.1

    # Third acquire will wait for next token (~0.05s)
    await limiter.acquire()
    total_elapsed = time.monotonic() - start
    assert total_elapsed >= 0.04
