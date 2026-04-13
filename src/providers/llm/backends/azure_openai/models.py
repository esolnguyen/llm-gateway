import logging
from typing import Any

from providers.models import AzureGenerateContentConfig, ModelBasicInfo

from .base import AzureOpenAILLMBase
from .batch import BatchProcessor

logger = logging.getLogger(__name__)


class AzureOpenAIGPT4(AzureOpenAILLMBase):
    """Azure OpenAI GPT-4 implementation with batch support."""

    def __init__(
        self,
        model_info: ModelBasicInfo,
        config: AzureGenerateContentConfig | None = None,
    ) -> None:
        super().__init__(model_info, config)
        self.batch_processor = BatchProcessor(self.client)

    def _build_batch_request_body(self, input_text: str) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "messages": [self._generate_message_structure(input_text)],
            "max_tokens": self.config.max_output_tokens,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }

    async def start_batch(self, jsonl_file: str | bytes) -> str:
        return await self.batch_processor.start_batch(jsonl_file, self.model_name)

    async def check_batch_status(
        self,
        job_identifier: str,
        poll_interval: int = 30,
        max_wait: int = 86400,
    ) -> str:
        return await self.batch_processor.check_batch_status(
            job_identifier, self.model_name, poll_interval, max_wait
        )

    async def check_batch_status_no_polling(self, job_identifier: str) -> str:
        return await self.batch_processor.check_batch_status_no_polling(job_identifier)

    async def save_batch_results(self, job_identifier: str, destination_path: str) -> None:
        await self.batch_processor.save_batch_results(job_identifier, destination_path)

    async def retrieve_batch_results(self, job_identifier: str) -> list[dict[str, Any]]:
        return await self.batch_processor.retrieve_batch_results(
            job_identifier, self.model_name
        )

    async def cleanup_old_files(self, max_age_days: int = 7) -> dict[str, int]:
        return await self.batch_processor.cleanup_old_files(max_age_days)

    def parse_jsonl_results(self, jsonl_file: str | bytes) -> list[dict[str, Any]]:
        return self.batch_processor.parse_jsonl_results(jsonl_file, self.model_name)

    def _append_jsonl_entry(
        self,
        batch_number: int,
        input_text: str,
        jsonl: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        custom_id = f"CALL_{batch_number}"

        if any(entry["custom_id"] == custom_id for entry in jsonl):
            logger.warning(f"Batch number {batch_number} already exists in JSONL.")
            return jsonl

        jsonl.append(
            {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/chat/completions",
                "body": self._build_batch_request_body(input_text),
            }
        )
        return jsonl


class AzureOpenAIGPT5(AzureOpenAILLMBase):
    """Azure OpenAI GPT-5 implementation with batch support."""

    def __init__(
        self,
        model_info: ModelBasicInfo,
        config: AzureGenerateContentConfig | None = None,
    ) -> None:
        super().__init__(model_info, config)
        self.batch_processor = BatchProcessor(self.client)

    def _build_batch_request_body(self, input_text: str) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "messages": [self._generate_message_structure(input_text)],
            "max_completion_tokens": self.config.max_output_tokens,
        }

    async def start_batch(self, jsonl_file: str | bytes) -> str:
        return await self.batch_processor.start_batch(jsonl_file, self.model_name)

    async def check_batch_status(
        self,
        job_identifier: str,
        poll_interval: int = 30,
        max_wait: int = 86400,
    ) -> str:
        return await self.batch_processor.check_batch_status(
            job_identifier, self.model_name, poll_interval, max_wait
        )

    async def check_batch_status_no_polling(self, job_identifier: str) -> str:
        return await self.batch_processor.check_batch_status_no_polling(job_identifier)

    async def save_batch_results(self, job_identifier: str, destination_path: str) -> None:
        await self.batch_processor.save_batch_results(job_identifier, destination_path)

    async def retrieve_batch_results(self, job_identifier: str) -> list[dict[str, Any]]:
        return await self.batch_processor.retrieve_batch_results(
            job_identifier, self.model_name
        )

    async def cleanup_old_files(self, max_age_days: int = 7) -> dict[str, int]:
        return await self.batch_processor.cleanup_old_files(max_age_days)

    def parse_jsonl_results(self, jsonl_file: str | bytes) -> list[dict[str, Any]]:
        return self.batch_processor.parse_jsonl_results(jsonl_file, self.model_name)

    def _append_jsonl_entry(
        self,
        batch_number: int,
        input_text: str,
        jsonl: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        custom_id = f"CALL_{batch_number}"

        if any(entry["custom_id"] == custom_id for entry in jsonl):
            logger.warning(f"Batch number {batch_number} already exists in JSONL.")
            return jsonl

        jsonl.append(
            {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/chat/completions",
                "body": self._build_batch_request_body(input_text),
            }
        )
        return jsonl
