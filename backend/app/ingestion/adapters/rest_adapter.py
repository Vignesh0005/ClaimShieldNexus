from collections.abc import AsyncIterator

import httpx

from app.ingestion.adapters.base import IngestionAdapter


class RESTAdapter(IngestionAdapter):
    """Pulls claims from a tenant's REST endpoint. Expects a JSON array, or an object with a list
    under `items_key` and an optional `next` URL for pagination."""

    name = "rest"

    def __init__(self, url: str, headers: dict[str, str] | None = None, items_key: str = "claims", max_pages: int = 100):
        self.url, self.headers, self.items_key, self.max_pages = url, headers or {}, items_key, max_pages

    async def records(self) -> AsyncIterator[dict]:
        url: str | None = self.url
        async with httpx.AsyncClient(timeout=30.0, headers=self.headers) as client:
            for _ in range(self.max_pages):
                if not url:
                    break
                response = await client.get(url)
                response.raise_for_status()
                body = response.json()
                items = body if isinstance(body, list) else body.get(self.items_key, [])
                for item in items:
                    yield item
                url = None if isinstance(body, list) else body.get("next")
