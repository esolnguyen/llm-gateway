"""Event bus interface and in-process implementation.

Swap the default `InMemoryEventBus` for a broker-backed bus (Redis Streams,
SQS, EventBridge) by calling `set_event_bus()` during application startup.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Awaitable[None]]


class EventBus(ABC):
    @abstractmethod
    async def publish(self, topic: str, event: Any) -> None: ...

    @abstractmethod
    def subscribe(self, topic: str, handler: Handler) -> None: ...


class InMemoryEventBus(EventBus):
    """Fire-and-forget asyncio fan-out bus for single-process deployments."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._handlers.setdefault(topic, []).append(handler)
        logger.debug(f"Subscribed {handler.__qualname__} to '{topic}'")

    async def publish(self, topic: str, event: Any) -> None:
        handlers = self._handlers.get(topic, [])
        if not handlers:
            logger.debug(f"No handlers registered for topic '{topic}'")
            return

        for handler in handlers:
            asyncio.create_task(self._run_handler(handler, event, topic))

    async def _run_handler(self, handler: Handler, event: Any, topic: str) -> None:
        try:
            await handler(event)
        except Exception as e:
            logger.error(
                f"Handler {handler.__qualname__} failed for topic '{topic}': {e}",
                exc_info=True,
            )


_default_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = InMemoryEventBus()
    return _default_bus


def set_event_bus(bus: EventBus) -> None:
    global _default_bus
    _default_bus = bus
