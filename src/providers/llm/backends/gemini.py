import io
import json
import logging

import filetype
from google import genai
from google.api_core import exceptions as google_exceptions
from google.genai import types
from overrides import override
from PIL import Image

from providers.exceptions import GeminiTransientError, LLMError
from providers.llm.base import LargeLanguageModelBase
from providers.models import LLMResponse, ModelBasicInfo

logger = logging.getLogger(__name__)


class GeminiLLM(LargeLanguageModelBase):
    def __init__(
        self,
        model_info: ModelBasicInfo,
        config: types.GenerateContentConfig | None = None,
    ) -> None:
        try:
            api_key = model_info.secret.api_key
            if not api_key:
                raise LLMError(
                    "GeminiLLMInitializationError", "API key missing in model info"
                )
            self.client = genai.Client(api_key=api_key)
            self.model_name = model_info.model_name
            self.config = config

        except Exception as e:
            logger.error(f"Failed to initialize GeminiLLM: {e}", exc_info=True)
            raise LLMError("Failed to initialize Gemini client", str(e)) from e

    async def _build_contents_for_file(self, prompt: str, file: bytes) -> list:
        try:
            file_size = len(file)
            kind = filetype.guess(file)
            detected_mime = kind.mime if kind else "application/octet-stream"

            logger.info(f"Processing file ({file_size} bytes), MIME: {detected_mime}")

            if detected_mime == "application/pdf":
                try:
                    pdf_part = types.Part.from_bytes(
                        data=file, mime_type="application/pdf"
                    )
                    return [pdf_part, prompt]
                except Exception as pdf_error:
                    logger.error(f"PDF processing failed: {pdf_error}", exc_info=True)
                    raise LLMError("Failed to process PDF", str(pdf_error)) from pdf_error

            if detected_mime.startswith("image/") or detected_mime == "application/octet-stream":
                try:
                    image = Image.open(io.BytesIO(file))
                    logger.debug(f"Loaded image: {image.format}, size: {image.size}")
                    return [image, prompt]
                except Exception as image_error:
                    if detected_mime.startswith("image/"):
                        logger.error(
                            f"Image processing failed: {image_error}", exc_info=True
                        )
                        raise LLMError(
                            "Failed to process image", str(image_error)
                        ) from image_error

            raise LLMError(f"Unsupported file type: {detected_mime}")
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Error building file contents: {e}", exc_info=True)
            raise LLMError("Failed to process file", str(e)) from e

    def _process_response(self, response: types.GenerateContentResponse) -> LLMResponse:
        try:
            if not response.candidates:
                feedback = getattr(response, "prompt_feedback", None)
                block_reason = getattr(feedback, "block_reason", "Unknown")
                safety_ratings = getattr(feedback, "safety_ratings", "N/A")

                error_msg = f"Response blocked. Reason: {block_reason}, Safety: {safety_ratings}"
                logger.error(error_msg)
                raise LLMError("Response blocked or empty", error_msg)

            usage_metadata = getattr(response, "usage_metadata", None)
            input_tokens = 0
            output_tokens = 0

            if usage_metadata:
                input_tokens = getattr(usage_metadata, "prompt_token_count", 0) or 0
                thought_tokens = getattr(usage_metadata, "thoughts_token_count", 0) or 0
                output_tokens = getattr(usage_metadata, "candidates_token_count", 0) or 0
                output_tokens += thought_tokens
            else:
                logger.warning("No usage metadata in response")

            response_content = ""
            candidate_content = getattr(response.candidates[0], "content", None)

            if candidate_content and getattr(candidate_content, "parts", None):
                response_content = "".join(
                    part.text
                    for part in candidate_content.parts
                    if getattr(part, "text", None)
                ).strip()

            if not response_content:
                logger.warning("Empty response content")
                raise LLMError("Empty response content")

            if self.config and getattr(self.config, "response_schema", None):
                try:
                    json.loads(response_content)
                except json.JSONDecodeError as json_err:
                    logger.error(f"Invalid JSON: {json_err}")
                    raise LLMError("Invalid JSON in response", response_content) from json_err

            return LLMResponse(
                content=response_content,
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
        logger.info(f"Calling Gemini model: {self.model_name}")

        try:
            if file:
                contents = await self._build_contents_for_file(prompt, file)
            else:
                contents = types.Content(
                    role="user", parts=[types.Part.from_text(text=prompt)]
                )
        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Error preparing request: {e}", exc_info=True)
            raise LLMError("Failed to prepare request", str(e)) from e

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name, contents=contents, config=self.config
            )
            return self._process_response(response)

        except (
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.InternalServerError,
        ) as e:
            error_type = type(e).__name__
            logger.error(f"Transient API error ({error_type}): {e}")
            raise GeminiTransientError(
                "GeminiTransientError", f"{error_type}: {str(e)}"
            ) from e

        except google_exceptions.GoogleAPICallError as e:
            context = "with file" if file else "without file"
            logger.error(f"API error {context}: {e}", exc_info=True)
            raise LLMError(f"API error {context}", str(e)) from e

        except LLMError:
            raise
