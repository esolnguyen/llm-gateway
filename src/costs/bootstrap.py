"""Wire cost handlers into the event bus at application startup.

Call `register_cost_handlers()` exactly once during application startup
(e.g. in FastAPI `lifespan`, a Lambda cold-start, or a script entrypoint).
"""
import logging

from costs.handlers import CostEventHandler
from shared.events.bus import EventBus, get_event_bus
from shared.events.events import LLM_RESPONSE_TOPIC, OCR_RESPONSE_TOPIC

logger = logging.getLogger(__name__)


def register_cost_handlers(
    bus: EventBus | None = None,
    handler: CostEventHandler | None = None,
) -> None:
    bus = bus or get_event_bus()
    handler = handler or CostEventHandler()

    bus.subscribe(LLM_RESPONSE_TOPIC, handler.on_llm_response)
    bus.subscribe(OCR_RESPONSE_TOPIC, handler.on_ocr_response)

    logger.info("Cost handlers registered on event bus")
