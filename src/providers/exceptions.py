class LLMError(Exception):
    """Base exception for LLM-related errors."""


class GeminiTransientError(LLMError):
    """Raised for transient errors from Gemini API."""


class OcrError(Exception):
    """Base exception for OCR-related errors."""


class OcrValidationError(OcrError):
    """Raised for OCR validation errors (invalid input, credentials, etc.)."""


class OcrServiceError(OcrError):
    """Raised for OCR service errors (API failures, processing errors, etc.)."""


class OcrTransientError(OcrError):
    """Raised for transient OCR errors (rate limits, temporary service unavailability)."""


class ServiceError(Exception):
    """Base exception for service-related errors."""


class CredentialNotFoundError(ServiceError):
    """Raised when no active credential exists for a requested model."""
