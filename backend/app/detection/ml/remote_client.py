import time
from dataclasses import dataclass, field

import httpx

from app.core.exceptions import MLServerUnavailable
from app.core.logging import logger


@dataclass
class MLPrediction:
    fraud_probability: float | None
    anomaly_score: float | None = None
    lof_score: float | None = None
    top_features: list[dict] = field(default_factory=list)
    model_version: str = "fallback_rules_only"
    degraded: bool = False


class CircuitBreaker:
    """Stops calling a failing dependency for recovery_timeout seconds after failure_threshold
    consecutive failures, then lets one request through to test it."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.opened_at: float | None = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.monotonic() - self.opened_at >= self.recovery_timeout:
            return False  # half-open: allow a trial call
        return True

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None


class RemoteMLClient:
    """Calls the model server on the training machine. Raises MLServerUnavailable on any failure
    so the caller can fall back to local scoring or rules only."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)

    async def _post(self, path: str, payload: dict) -> dict:
        if self.circuit_breaker.is_open():
            raise MLServerUnavailable("Model server circuit is open.")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}{path}", json=payload)
                response.raise_for_status()
                self.circuit_breaker.record_success()
                return response.json()
        except Exception as exc:  # noqa: BLE001
            self.circuit_breaker.record_failure()
            logger.error("ml_server_error", path=path, error=str(exc))
            raise MLServerUnavailable() from exc

    async def predict(self, features: dict) -> MLPrediction:
        data = await self._post("/predict", {"features": features})
        return MLPrediction(
            fraud_probability=data.get("fraud_probability"),
            anomaly_score=data.get("anomaly_score"),
            lof_score=data.get("lof_score"),
            top_features=data.get("top_features", []),
            model_version=data.get("model_version", "remote"),
        )

    async def find_similar(self, claim_text: str, k: int = 5) -> list:
        return (await self._post("/similar", {"claim_text": claim_text, "k": k})).get("similar_cases", [])

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                return (await client.get(f"{self.base_url}/health")).status_code == 200
        except Exception:  # noqa: BLE001
            return False
