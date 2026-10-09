"""AWS SQS consumer: the event-driven ingestion path.

Run as its own process:  python -m app.ingestion.adapters.sqs_adapter

Message body: {"tenant": "<tenant slug>", "claim": {...}}  (or "claims": [...]).
A message is deleted only after its claims are stored, so a crash mid-batch leads to redelivery,
which the idempotency check absorbs. Messages that fail validation are left on the queue and reach
the dead-letter queue through the queue's redrive policy rather than being dropped here."""
import asyncio
import json
from collections.abc import AsyncIterator

import anyio

from app.config import get_settings
from app.core.logging import configure_logging, logger
from app.ingestion.adapters.base import IngestionAdapter


class SQSAdapter(IngestionAdapter):
    name = "sqs"

    def __init__(self, queue_url: str | None = None, wait_seconds: int = 20, batch_size: int = 10):
        import boto3

        settings = get_settings()
        self.queue_url = queue_url or settings.sqs_queue_url
        if not self.queue_url:
            raise RuntimeError("SQS_QUEUE_URL is not set.")
        self.client = boto3.client("sqs", region_name=settings.aws_region)
        self.wait_seconds, self.batch_size = wait_seconds, batch_size

    async def receive(self) -> list[dict]:
        response = await anyio.to_thread.run_sync(
            lambda: self.client.receive_message(QueueUrl=self.queue_url, MaxNumberOfMessages=self.batch_size, WaitTimeSeconds=self.wait_seconds)
        )
        return response.get("Messages", [])

    async def ack(self, message: dict) -> None:
        await anyio.to_thread.run_sync(lambda: self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=message["ReceiptHandle"]))

    async def records(self) -> AsyncIterator[dict]:
        for message in await self.receive():
            body = json.loads(message["Body"])
            for claim in body.get("claims") or [body.get("claim")]:
                if claim:
                    yield claim


async def consume_forever() -> None:
    from app.core.exceptions import ClaimShieldException
    from app.db.session import session_scope
    from app.services import claim_service, tenant_service

    adapter = SQSAdapter()
    logger.info("sqs_consumer_started", queue=adapter.queue_url)
    while True:
        try:
            messages = await adapter.receive()
        except Exception as exc:  # noqa: BLE001
            logger.error("sqs_receive_failed", error=str(exc))
            await asyncio.sleep(5)
            continue
        for message in messages:
            try:
                body = json.loads(message["Body"])
                async with session_scope() as db:
                    tenant = await tenant_service.get_by_slug(db, body["tenant"])
                    db.info["tenant_id"] = tenant.id
                    for record in body.get("claims") or [body["claim"]]:
                        await claim_service.ingest_record(db, tenant, record, source="sqs", process=True)
                await adapter.ack(message)
            except (ClaimShieldException, KeyError, json.JSONDecodeError) as exc:
                logger.warning("sqs_message_rejected", message_id=message.get("MessageId"), error=str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.error("sqs_message_failed", message_id=message.get("MessageId"), error=str(exc))


if __name__ == "__main__":
    configure_logging()
    asyncio.run(consume_forever())
