from abc import ABC, abstractmethod

from providers.models import LLMResponse


class LargeLanguageModelBase(ABC):
    @abstractmethod
    async def call_llm(self, prompt: str, file: bytes | None = None) -> LLMResponse:
        """Call the LLM with the given prompt and optional file."""
