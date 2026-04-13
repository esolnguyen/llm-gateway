"""Cost event persistence."""
import logging
from decimal import Decimal

from costs.schema import CostEvent
from shared.db.session import get_session

logger = logging.getLogger(__name__)


class CostEventRepository:
    async def insert(
        self,
        *,
        module_name: str,
        service_name: str,
        user_id: str,
        organisation_id: str,
        model_name: str,
        capability: str,
        units: dict,
        cost_amount: Decimal,
        currency: str = "USD",
        external_ref_type: str | None = None,
        external_ref_id: str | None = None,
        event_metadata: dict | None = None,
    ) -> CostEvent:
        async with get_session() as session:
            event = CostEvent(
                module_name=module_name,
                service_name=service_name,
                user_id=user_id,
                organisation_id=organisation_id,
                model_name=model_name,
                capability=capability,
                units=units,
                cost_amount=cost_amount,
                currency=currency,
                external_ref_type=external_ref_type,
                external_ref_id=external_ref_id,
                event_metadata=event_metadata,
            )
            session.add(event)
            await session.flush()
            await session.refresh(event)
            logger.info(
                f"Persisted cost event {event.id} "
                f"model={model_name} cost={cost_amount} {currency}"
            )
            return event
