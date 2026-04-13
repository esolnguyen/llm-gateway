"""Pricing data access."""
import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from costs.schema import ModelPricing
from shared.db.session import get_session

logger = logging.getLogger(__name__)


class PricingNotFoundError(Exception):
    pass


class PricingRepository:
    async def get_price(
        self,
        model_name: str,
        capability: str,
        unit_type: str,
        at: datetime | None = None,
    ) -> Decimal:
        at = at or datetime.now(timezone.utc)

        async with get_session() as session:
            stmt = (
                select(ModelPricing.price_per_unit)
                .where(ModelPricing.model_name == model_name)
                .where(ModelPricing.capability == capability)
                .where(ModelPricing.unit_type == unit_type)
                .where(ModelPricing.effective_from <= at)
                .where(
                    (ModelPricing.effective_to.is_(None))
                    | (ModelPricing.effective_to > at)
                )
                .order_by(ModelPricing.effective_from.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            price = result.scalar_one_or_none()

        if price is None:
            raise PricingNotFoundError(
                f"No pricing for model={model_name} capability={capability} "
                f"unit_type={unit_type} at={at.isoformat()}"
            )
        return price
