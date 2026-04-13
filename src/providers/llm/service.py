"""LLM service: fetches credentials, calls the provider, emits a response event."""
import logging
from typing import Any

from providers.credentials.repository import (
    CredentialRepository,
    get_credential_repository,
)
from providers.llm.factory import LargeLanguageModelFactory
from providers.models import (
    GenerateContentConfig,
    LLMResponse,
    ModelBasicInfo,
    OrganisationInfo,
    SecretCredentialInfo,
    UserInfo,
)
from shared.events.bus import EventBus, get_event_bus
from shared.events.events import LLM_RESPONSE_TOPIC, LLMResponseEvent

logger = logging.getLogger(__name__)


class LLMService:
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
        self._factory = LargeLanguageModelFactory()
        logger.debug(
            f"LLMService initialised for module={module_name} service={service_name}"
        )

    async def call_llm(
        self,
        model_name: str,
        prompt: str,
        config: GenerateContentConfig | None = None,
        file: bytes | None = None,
        external_ref_type: str | None = None,
        external_ref_id: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        logger.info(f"Calling LLM with model: {model_name}")

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

        llm = self._factory.create_llm(model_info, config)
        response = await llm.call_llm(prompt=prompt, file=file)
        logger.info(
            f"LLM call complete: input={response.input_tokens} "
            f"output={response.output_tokens}"
        )

        event = LLMResponseEvent(
            module_name=self.module_name,
            service_name=self.service_name,
            user_id=self.user_info.id,
            organisation_id=self.organisation_info.id,
            model_name=model_name,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            external_ref_type=external_ref_type,
            external_ref_id=external_ref_id,
            event_metadata=event_metadata,
        )
        await self._bus.publish(LLM_RESPONSE_TOPIC, event)

        return response
