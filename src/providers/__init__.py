"""Provider library: LLM and OCR integrations with credential lookup and event emission."""
__version__ = "1.0.0"

from providers.exceptions import (
    GeminiTransientError,
    LLMError,
    OcrError,
    OcrServiceError,
    OcrTransientError,
    OcrValidationError,
    ServiceError,
)
from providers.llm.factory import LargeLanguageModelFactory
from providers.llm.service import LLMService
from providers.models import (
    AzureDocumentIntelligenceConfig,
    AzureGenerateContentConfig,
    FigureElement,
    GenerateContentConfig,
    LLMResponse,
    ModelBasicInfo,
    OCRConfig,
    OCRConfigBase,
    OcrPageElement,
    OcrResponse,
    OrganisationInfo,
    SecretCredentialInfo,
    TableCell,
    TableElement,
    UserInfo,
    WordElement,
)
from providers.ocr.factory import OCRFactory
from providers.ocr.service import OCRService

__all__ = [
    "LLMService",
    "OCRService",
    "LargeLanguageModelFactory",
    "OCRFactory",
    "LLMResponse",
    "AzureGenerateContentConfig",
    "GenerateContentConfig",
    "OCRConfigBase",
    "AzureDocumentIntelligenceConfig",
    "OCRConfig",
    "OcrResponse",
    "OcrPageElement",
    "WordElement",
    "TableElement",
    "TableCell",
    "FigureElement",
    "ModelBasicInfo",
    "SecretCredentialInfo",
    "UserInfo",
    "OrganisationInfo",
    "LLMError",
    "GeminiTransientError",
    "OcrError",
    "OcrValidationError",
    "OcrServiceError",
    "OcrTransientError",
    "ServiceError",
]
