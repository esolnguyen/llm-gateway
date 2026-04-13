"""Convert raw usage units into a monetary cost via the pricing repository."""
import logging
from decimal import Decimal

from costs.pricing.repository import PricingRepository

logger = logging.getLogger(__name__)


class CostCalculator:
    def __init__(self, pricing_repository: PricingRepository | None = None) -> None:
        self._pricing = pricing_repository or PricingRepository()

    async def calculate(
        self,
        model_name: str,
        capability: str,
        units: dict[str, int],
    ) -> Decimal:
        total = Decimal(0)
        for unit_type, quantity in units.items():
            if quantity <= 0:
                continue
            price = await self._pricing.get_price(model_name, capability, unit_type)
            total += price * Decimal(quantity)
        logger.debug(
            f"Calculated cost for {model_name}/{capability}: {total} "
            f"(units={units})"
        )
        return total
