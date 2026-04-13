"""OCR service: fetches credentials, runs extraction, emits a response event."""
import logging
from typing import Any

from providers.credentials.repository import (
    CredentialRepository,
    get_credential_repository,
)
from providers.models import (
    ModelBasicInfo,
    OCRConfig,
    OcrResponse,
    OrganisationInfo,
    SecretCredentialInfo,
    UserInfo,
)
from providers.ocr.factory import OCRFactory
from shared.events.bus import EventBus, get_event_bus
from shared.events.events import OCR_RESPONSE_TOPIC, OCRResponseEvent

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(
        self,
        module_name: str,
        service_name: str,
        user_info: UserInfo,
        organisation_info: OrganisationInfo,
        credential_repository: CredentialRepository | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.module_name = module_name
        self.service_name = service_name
        self.user_info = user_info
        self.organisation_info = organisation_info
        self._credentials = credential_repository or get_credential_repository()
        self._bus = event_bus or get_event_bus()
        self._factory = OCRFactory()

    async def extract_document(
        self,
        model_name: str,
        document_bytes: bytes,
        config: OCRConfig | None = None,
        external_ref_type: str | None = None,
        external_ref_id: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> OcrResponse:
        logger.info(f"Extracting document with model: {model_name}")

        credential = await self._credentials.get(model_name)
        model_info = ModelBasicInfo(
            provider=credential.provider,
            model_name=credential.model_name,
            secret=SecretCredentialInfo(
                api_key=credential.api_key,
                api_endpoint=credential.api_endpoint,
                api_version=credential.api_version,
            ),
        )

        ocr = self._factory.create_ocr(model_info, config)
        response = await ocr.extract(document_bytes)
        logger.info(f"OCR extraction complete: {response.no_pages} pages")

        event = OCRResponseEvent(
            module_name=self.module_name,
            service_name=self.service_name,
            user_id=self.user_info.id,
            organisation_id=self.organisation_info.id,
            model_name=model_name,
            pages=response.no_pages,
            external_ref_type=external_ref_type,
            external_ref_id=external_ref_id,
            event_metadata=event_metadata,
        )
        await self._bus.publish(OCR_RESPONSE_TOPIC, event)

        return response
