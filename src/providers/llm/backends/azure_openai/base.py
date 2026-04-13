import json
import logging
import time
from abc import abstractmethod
from typing import Any

from openai import AsyncAzureOpenAI
from overrides import override

from providers.exceptions import LLMError
from providers.llm.base import LargeLanguageModelBase
from providers.models import (
    AzureGenerateContentConfig,
    LLMResponse,
    ModelBasicInfo,
)

from .utils import MIME_PDF, data_url, guess_mime

logger = logging.getLogger(__name__)


class AzureOpenAILLMBase(LargeLanguageModelBase):
    """Abstract base for Azure OpenAI LLM implementations."""

    def __init__(
        self,
        model_info: ModelBasicInfo,
        config: AzureGenerateContentConfig | None = None,
    ) -> None:
        if not model_info.secret.api_endpoint:
            raise LLMError(
                "AzureOpenAILLMInitializationError",
                "API endpoint missing in model info",
            )
        try:
            self.client = AsyncAzureOpenAI(
                api_key=model_info.secret.api_key,
                api_version=model_info.secret.api_version,
                azure_endpoint=model_info.secret.api_endpoint,
            )

            self.model_name = model_info.model_name
            self.config = config if config is not None else AzureGenerateContentConfig()

            if self.config.instructions is None and self.config.system_instruction is not None:
                self.config.instructions = self.config.system_instruction
            if self.config.temperature is None:
                self.config.temperature = 0.0
            if self.config.max_output_tokens is None:
                self.config.max_output_tokens = 10_000

            logger.info(
                f"Initialised {self.__class__.__name__} model={self.model_name} "
                f"temperature={self.config.temperature:.2f} "
                f"max_tokens={self.config.max_output_tokens}"
            )
        except Exception as e:
            logger.error(
                f"Failed to initialise {self.__class__.__name__}: {e}", exc_info=True
            )
            raise LLMError("Failed to initialise Azure OpenAI client", str(e)) from e

    def _build_content(self, prompt: str, file: bytes | None = None) -> list:
        try:
            enhanced_prompt = prompt
            if "json" not in prompt.lower():
                enhanced_prompt = f"{prompt}\n\nPlease provide your response in JSON format."

            content: list[dict[str, Any]] = [{"type": "text", "text": enhanced_prompt}]

            if file is not None:
                mime = guess_mime(file)
                if mime == MIME_PDF:
                    content.append({"type": "file", "file_data": data_url(file, mime)})
                elif mime.startswith("image/"):
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url(file, mime)}}
                    )
                else:
                    raise LLMError(
                        "Unsupported file type",
                        f"Detected mime: {mime}. Supported: PDF, PNG, JPEG, WEBP",
                    )

            return content

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Error building content: {e}", exc_info=True)
            raise LLMError("Failed to build request content", str(e)) from e

    def _build_request(self, content: list) -> dict[str, Any]:
        try:
            messages: list[dict[str, Any]] = []

            if self.config.instructions is not None:
                messages.append({"role": "system", "content": self.config.instructions})

            messages.append({"role": "user", "content": content})

            req: dict[str, Any] = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": self.config.max_output_tokens,
            }

            if self.config.reasoning is not None:
                req["reasoning"] = self.config.reasoning
            else:
                if self.config.temperature is not None:
                    req["temperature"] = self.config.temperature
                if self.config.top_p is not None:
                    req["top_p"] = self.config.top_p

            optional_params = {
                "seed": self.config.seed,
                "metadata": self.config.metadata,
                "parallel_tool_calls": self.config.parallel_tool_calls,
                "service_tier": self.config.service_tier,
                "store": self.config.store,
                "stream_options": self.config.stream_options,
                "tool_choice": self.config.tool_choice,
                "tools": self.config.tools,
                "top_logprobs": self.config.top_logprobs,
                "truncation": self.config.truncation,
                "user": self.config.user,
                "background": self.config.background,
                "max_tool_calls": self.config.max_tool_calls,
                "prompt_cache_key": self.config.prompt_cache_key,
                "prompt_cache_retention": self.config.prompt_cache_retention,
                "safety_identifier": self.config.safety_identifier,
            }

            for name, value in optional_params.items():
                if value is not None:
                    req[name] = value

            return req

        except Exception as e:
            logger.error(f"Error building request: {e}", exc_info=True)
            raise LLMError("Failed to build API request", str(e)) from e

    def _process_response(self, response, duration: float) -> LLMResponse:
        try:
            if not response.choices or len(response.choices) == 0:
                raise LLMError("Empty response content", "No choices in response")

            output_text = response.choices[0].message.content
            if not output_text:
                raise LLMError("Empty response content", "Message content is empty")

            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            logger.info(
                f"Response received. Duration: {duration:.2f}s, "
                f"Tokens - Input: {input_tokens}, Output: {output_tokens}"
            )

            try:
                json.loads(output_text)
            except json.JSONDecodeError as json_err:
                logger.error(f"Invalid JSON: {json_err}")
                raise LLMError("Invalid JSON in response", output_text) from json_err

            return LLMResponse(
                content=output_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Error processing response: {e}", exc_info=True)
            raise LLMError("Failed to process response", str(e)) from e

    @override
    async def call_llm(self, prompt: str, file: bytes | None = None) -> LLMResponse:
        if not prompt or not prompt.strip():
            raise LLMError("Prompt cannot be empty", "Prompt validation failed")

        logger.info(f"Calling Azure OpenAI model: {self.model_name}")

        try:
            content = self._build_content(prompt, file)
            request = self._build_request(content)
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Error preparing request: {e}", exc_info=True)
            raise LLMError("Failed to prepare request", str(e)) from e

        start_time = time.time()

        try:
            response = await self.client.chat.completions.create(**request)
            duration = time.time() - start_time
            return self._process_response(response, duration)
        except LLMError:
            raise
        except Exception as e:
            context = "with file" if file else "without file"
            logger.error(f"API error {context}: {e}", exc_info=True)
            raise LLMError(
                f"Azure OpenAI API error {context}",
                f"Error type: {type(e).__name__}, message: {e}",
            ) from e

    @abstractmethod
    def _build_batch_request_body(self, input_text: str) -> dict[str, Any]:
        """Build batch request body. Must be implemented by subclasses."""

    def _generate_message_structure(self, input_text: str) -> dict[str, Any]:
        return {"role": "user", "content": input_text}
