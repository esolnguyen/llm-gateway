"""Domain events published by providers and consumed by costs."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

LLM_RESPONSE_TOPIC = "llm.response"
OCR_RESPONSE_TOPIC = "ocr.response"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class LLMResponseEvent:
    module_name: str
    service_name: str
    user_id: str
    organisation_id: str
    model_name: str
    input_tokens: int
    output_tokens: int
    external_ref_type: str | None = None
    external_ref_id: str | None = None
    event_metadata: dict[str, Any] | None = None
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utcnow)


@dataclass
class OCRResponseEvent:
    module_name: str
    service_name: str
    user_id: str
    organisation_id: str
    model_name: str
    pages: int
    external_ref_type: str | None = None
    external_ref_id: str | None = None
    event_metadata: dict[str, Any] | None = None
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=_utcnow)
