import logging

from google.genai import types

from providers.exceptions import LLMError
from providers.llm.backends.azure_openai import create_azure_openai_llm
from providers.llm.base import LargeLanguageModelBase
from providers.models import (
    AzureGenerateContentConfig,
    GenerateContentConfig,
    ModelBasicInfo,
)

logger = logging.getLogger(__name__)


class LargeLanguageModelFactory:
    def create_llm(
        self,
        info: ModelBasicInfo,
        config: GenerateContentConfig = None,
    ) -> LargeLanguageModelBase:
        logger.info(
            f"Creating LLM instance for provider: {info.provider}, model: {info.model_name}"
        )

        try:
            if info.provider == "microsoft":
                azure_config: AzureGenerateContentConfig | None = None
                if config is not None:
                    if isinstance(config, AzureGenerateContentConfig):
                        azure_config = config
                    else:
                        azure_config = AzureGenerateContentConfig(**config.model_dump())
                return create_azure_openai_llm(info, azure_config)

            if info.provider == "google":
                from providers.llm.backends.gemini import GeminiLLM

                google_config: types.GenerateContentConfig | None = None
                if config is not None:
                    if isinstance(config, types.GenerateContentConfig):
                        google_config = config
                    else:
                        google_config = types.GenerateContentConfig(
                            **config.model_dump(exclude_none=True)
                        )
                return GeminiLLM(info, google_config)

            raise LLMError(
                "Unsupported provider",
                f"Provider '{info.provider}' is not implemented. Supported: microsoft, google",
            )
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Failed to create LLM instance: {e}", exc_info=True)
            raise LLMError("Failed to create LLM instance", str(e)) from e
