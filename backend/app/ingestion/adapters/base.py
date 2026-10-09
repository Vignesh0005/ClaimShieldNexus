from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class IngestionAdapter(ABC):
    """Turns one source format into canonical-ish claim dicts. Field mapping, normalisation and
    validation happen afterwards in the shared ingest path, so an adapter only has to parse."""

    name: str = "base"

    @abstractmethod
    def records(self) -> AsyncIterator[dict]:
        """Yields one dict per claim."""
