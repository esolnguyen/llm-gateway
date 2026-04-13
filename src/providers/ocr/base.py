from abc import ABC, abstractmethod

from providers.models import OcrResponse


class BaseOCR(ABC):
    def __init__(self, min_ocr_confidence: int) -> None:
        if not 0 <= min_ocr_confidence <= 100:
            raise ValueError("min_ocr_confidence must be between 0 and 100")
        self.min_ocr_confidence = min_ocr_confidence

    @abstractmethod
    async def extract(self, document: bytes) -> OcrResponse: ...
