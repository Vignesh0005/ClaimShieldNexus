import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from app.config import get_settings
from app.core.logging import logger

Handler = Callable[[str, dict], Awaitable[None]]


class EventBus:
    """Publishes domain events (claim.processed, case.created, audit.logged, ...).

    In-process subscribers always run. When SNS_TOPIC_ARN is configured the event is also sent to
    SNS so other systems can react. Publishing never raises: a broken subscriber must not fail the
    request that produced the event."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._sns = None

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers[topic].append(handler)

    def _sns_client(self):
        settings = get_settings()
        if not settings.sns_topic_arn:
            return None
        if self._sns is None:
            import boto3

            self._sns = boto3.client("sns", region_name=settings.aws_region)
        return self._sns

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        for handler in self._handlers.get(topic, []) + self._handlers.get("*", []):
            try:
                await handler(topic, payload)
            except Exception as exc:  # noqa: BLE001
                logger.error("event_handler_failed", topic=topic, error=str(exc))
        try:
            client = self._sns_client()
            if client is not None:
                import anyio

                await anyio.to_thread.run_sync(
                    lambda: client.publish(
                        TopicArn=get_settings().sns_topic_arn,
                        Message=json.dumps(payload, default=str),
                        MessageAttributes={"topic": {"DataType": "String", "StringValue": topic}},
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("sns_publish_failed", topic=topic, error=str(exc))


event_bus = EventBus()
