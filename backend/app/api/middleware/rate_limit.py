import time

from app.config import get_settings
from app.core.cache import cache
from app.core.exceptions import RateLimited
from app.core.security import Principal


async def enforce_rate_limit(principal: Principal) -> None:
    """Fixed one-minute window per tenant and caller. Shared across API processes when Redis is
    configured; per process otherwise."""
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    window = int(time.time() // 60)
    count = await cache.incr(f"rl:{principal.tenant_id}:{principal.subject}:{window}", ttl=90)
    if count > limit:
        raise RateLimited(f"Rate limit of {limit} requests per minute exceeded. Try again in under a minute.", retry_after_seconds=60 - int(time.time() % 60))
