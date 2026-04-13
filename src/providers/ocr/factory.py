import logging

from providers.exceptions import OcrError
from providers.models import (
    AzureDocumentIntelligenceConfig,
    ModelBasicInfo,
    OCRConfigBase,
)
from providers.ocr.base import BaseOCR

logger = logging.getLogger(__name__)


class OCRFactory:
    def create_ocr(
        self,
        info: ModelBasicInfo,
        config: OCRConfigBase | None = None,
    ) -> BaseOCR:
        logger.info(
            f"Creating OCR instance for provider: {info.provider}, model: {info.model_name}"
        )

        try:
            if info.provider in ("microsoft", "microsoft-ocr"):
                from providers.ocr.backends.di import DocumentIntelligenceExtractor

                azure_config: AzureDocumentIntelligenceConfig | None = None
                if config is not None:
                    if isinstance(config, AzureDocumentIntelligenceConfig):
                        azure_config = config
                    else:
                        azure_config = AzureDocumentIntelligenceConfig(**config.model_dump())
                return DocumentIntelligenceExtractor(info, azure_config)

            raise OcrError(
                "Unsupported provider",
                f"Provider '{info.provider}' is not implemented. Supported: microsoft",
            )
        except OcrError:
            raise
        except Exception as e:
            logger.error(f"Failed to create OCR instance: {e}", exc_info=True)
            raise OcrError("Failed to create OCR instance", str(e)) from e
