"""Event handlers that consume provider events and persist cost records."""
import logging

from costs.pricing.calculator import CostCalculator
from costs.repository import CostEventRepository
from providers.models import Capability
from shared.events.events import LLMResponseEvent, OCRResponseEvent

logger = logging.getLogger(__name__)


class CostEventHandler:
    def __init__(
        self,
        calculator: CostCalculator | None = None,
        repository: CostEventRepository | None = None,
    ) -> None:
        self._calculator = calculator or CostCalculator()
        self._repository = repository or CostEventRepository()

    async def on_llm_response(self, event: LLMResponseEvent) -> None:
        units = {
            "input_tokens": event.input_tokens,
            "output_tokens": event.output_tokens,
        }
        await self._handle(event, Capability.CHAT.value, units)

    async def on_ocr_response(self, event: OCRResponseEvent) -> None:
        units = {"pages": event.pages}
        await self._handle(event, Capability.OCR.value, units)

    async def _handle(self, event, capability: str, units: dict[str, int]) -> None:
        try:
            cost = await self._calculator.calculate(
                model_name=event.model_name,
                capability=capability,
                units=units,
            )
        except Exception as e:
            logger.error(
                f"Failed to calculate cost for event {event.event_id} "
                f"({capability}/{event.model_name}): {e}",
                exc_info=True,
            )
            return

        try:
            await self._repository.insert(
                module_name=event.module_name,
                service_name=event.service_name,
                user_id=event.user_id,
                organisation_id=event.organisation_id,
                model_name=event.model_name,
                capability=capability,
                units=units,
                cost_amount=cost,
                external_ref_type=event.external_ref_type,
                external_ref_id=event.external_ref_id,
                event_metadata=event.event_metadata,
            )
        except Exception as e:
            logger.error(
                f"Failed to persist cost event for {event.event_id}: {e}",
                exc_info=True,
            )
