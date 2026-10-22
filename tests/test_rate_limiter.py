import asyncio
import pytest
from bot.utils.rate_limiter import UserRateLimiter


@pytest.mark.asyncio
async def test_user_rate_limiter_allows_first_request():
    limiter = UserRateLimiter(cooldown_seconds=2)
    allowed, remaining = await limiter.check(user_id=101)
    assert allowed is True
    assert remaining == 0.0


@pytest.mark.asyncio
async def test_user_rate_limiter_blocks_immediate_repeat():
    limiter = UserRateLimiter(cooldown_seconds=2)
    allowed1, _ = await limiter.check(user_id=102)
    assert allowed1 is True

    allowed2, remaining = await limiter.check(user_id=102)
    assert allowed2 is False
    assert remaining > 0.0


@pytest.mark.asyncio
async def test_user_rate_limiter_separate_users():
    limiter = UserRateLimiter(cooldown_seconds=2)
    allowed_u1, _ = await limiter.check(user_id=201)
    allowed_u2, _ = await limiter.check(user_id=202)
    assert allowed_u1 is True
    assert allowed_u2 is True
