import json
import time
from typing import Any

from app.config import get_settings
from app.core.logging import logger


class Cache:
    """Redis when REDIS_URL is set, otherwise a per-process dict. The in-memory form is correct for
    a single API process only; rate limits and idempotency keys are not shared across processes."""

    def __init__(self) -> None:
        self._redis = None
        self._memory: dict[str, tuple[float | None, str]] = {}

    async def connect(self) -> None:
        url = get_settings().redis_url
        if not url:
            return
        import redis.asyncio as redis

        self._redis = redis.from_url(url, decode_responses=True)

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    async def ping(self) -> bool:
        if self._redis is None:
            return True
        try:
            return bool(await self._redis.ping())
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_ping_failed", error=str(exc))
            return False

    async def get(self, key: str) -> Any | None:
        if self._redis is not None:
            raw = await self._redis.get(key)
            return json.loads(raw) if raw is not None else None
        item = self._memory.get(key)
        if item is None:
            return None
        expires, raw = item
        if expires is not None and expires < time.monotonic():
            self._memory.pop(key, None)
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        raw = json.dumps(value, default=str)
        if self._redis is not None:
            await self._redis.set(key, raw, ex=ttl)
        else:
            self._memory[key] = (time.monotonic() + ttl if ttl else None, raw)

    async def set_if_absent(self, key: str, value: Any, ttl: int) -> bool:
        """Atomic claim of a key. Returns False when it was already taken."""
        if self._redis is not None:
            return bool(await self._redis.set(key, json.dumps(value, default=str), ex=ttl, nx=True))
        if await self.get(key) is not None:
            return False
        await self.set(key, value, ttl)
        return True

    async def incr(self, key: str, ttl: int) -> int:
        if self._redis is not None:
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl, nx=True)
            return int((await pipe.execute())[0])
        current = int(await self.get(key) or 0) + 1
        expires = self._memory.get(key, (None, ""))[0] or time.monotonic() + ttl
        self._memory[key] = (expires, json.dumps(current))
        return current

    async def delete(self, key: str) -> None:
        if self._redis is not None:
            await self._redis.delete(key)
        else:
            self._memory.pop(key, None)

    def clear_memory(self) -> None:
        self._memory.clear()


cache = Cache()
