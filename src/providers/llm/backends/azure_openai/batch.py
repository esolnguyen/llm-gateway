import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from openai import AsyncAzureOpenAI

from providers.exceptions import LLMError

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles batch job creation, polling, and result retrieval."""

    def __init__(self, client: AsyncAzureOpenAI) -> None:
        self.client = client

    async def start_batch(self, jsonl_file: str | bytes, model_name: str) -> str:
        try:
            if isinstance(jsonl_file, bytes):
                file = await self.client.files.create(
                    file=("batch.jsonl", jsonl_file),
                    purpose="batch",
                    extra_body={
                        "expires_after": {"seconds": 1209600, "anchor": "created_at"}
                    },
                )
            else:
                with open(jsonl_file, "rb") as f:
                    file = await self.client.files.create(
                        file=f,
                        purpose="batch",
                        extra_body={
                            "expires_after": {
                                "seconds": 1209600,
                                "anchor": "created_at",
                            }
                        },
                    )

            logger.debug(f"Uploaded file: {file.filename}")
            logger.info(
                f"File expiration: "
                f"{datetime.fromtimestamp(file.expires_at) if file.expires_at else 'Not set'}"
            )

            batch_response = await self.client.batches.create(
                input_file_id=file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
                extra_body={
                    "output_expires_after": {
                        "seconds": 1209600,
                        "anchor": "created_at",
                    }
                },
            )

            batch_id = batch_response.id
            logger.debug(f"Created batch job: {batch_id}")
            return batch_id

        except Exception as e:
            logger.error(f"Error starting batch: {e}", exc_info=True)
            raise LLMError("Failed to start batch", str(e)) from e

    async def check_batch_status(
        self,
        job_identifier: str,
        model_name: str,
        poll_interval: int = 30,
        max_wait: int = 86400,
    ) -> str:
        try:
            batch_response = await self.client.batches.retrieve(job_identifier)
            status = batch_response.status
            elapsed = 0

            while status not in ("completed", "failed", "cancelled") and elapsed < max_wait:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                batch_response = await self.client.batches.retrieve(job_identifier)
                status = batch_response.status
                logger.info(
                    f"Batch {job_identifier} - Model: {model_name}, "
                    f"Status: {status}, Elapsed: {elapsed}s"
                )

            if batch_response.status == "failed":
                errors = getattr(batch_response, "errors", None)
                if errors:
                    for error in errors.data:
                        logger.error(f"Error code {error.code}: {error.message}")

            logger.info(f"Batch {job_identifier} completed with status: {status}")
            return status

        except Exception as e:
            logger.error(f"Error checking batch status: {e}", exc_info=True)
            raise LLMError("Failed to check batch status", str(e)) from e

    async def check_batch_status_no_polling(self, job_identifier: str) -> str:
        try:
            batch_response = await self.client.batches.retrieve(job_identifier, timeout=60)
            return batch_response.status
        except Exception as e:
            logger.error(f"Error checking batch status: {e}", exc_info=True)
            raise LLMError("Failed to check batch status", str(e)) from e

    async def save_batch_results(
        self, job_identifier: str, destination_path: str
    ) -> None:
        try:
            batch_response = await self.client.batches.retrieve(job_identifier)
            output_file_id = batch_response.output_file_id or batch_response.error_file_id

            if not output_file_id:
                raise LLMError("No output file", "Batch has no output or error file")

            file_response = await self.client.files.content(output_file_id)
            with open(destination_path, "w", encoding="utf-8") as f:
                f.write(file_response.text.strip())

            logger.info(f"Batch results saved to {destination_path}")

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Error saving batch results: {e}", exc_info=True)
            raise LLMError("Failed to save batch results", str(e)) from e

    async def retrieve_batch_results(
        self, job_identifier: str, model_name: str
    ) -> list[dict[str, Any]]:
        try:
            batch = await self.client.batches.retrieve(job_identifier)
            file_id = batch.output_file_id or batch.error_file_id

            if not file_id:
                raise LLMError("No output file", "Batch has no output or error file")

            resp = await self.client.files.content(file_id)
            raw_bytes = resp.read()
            text = raw_bytes.decode("utf-8", errors="replace").strip()

            results: list[dict] = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.error(f"JSONL parse error: {e} line={line[:200]}")

            await self._cleanup_batch_resources(job_identifier, batch.input_file_id, file_id)
            return results

        except LLMError:
            raise
        except Exception as e:
            logger.error(f"Error retrieving batch results: {e}", exc_info=True)
            raise LLMError("Failed to retrieve batch results", str(e)) from e

    async def _cleanup_batch_resources(
        self, batch_id: str, input_file_id: str, output_file_id: str
    ) -> None:
        try:
            await self.client.batches.cancel(batch_id)
            logger.info(f"Cancelled batch job: {batch_id}")
        except Exception as e:
            if "already" not in str(e).lower() and "cannot" not in str(e).lower():
                logger.warning(f"Failed to cancel batch {batch_id}: {str(e)}")

        for file_id in [input_file_id, output_file_id]:
            if file_id:
                try:
                    await self.client.files.delete(file_id)
                    logger.info(f"Deleted file: {file_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_id}: {str(e)}")

    async def cleanup_old_files(self, max_age_days: int = 7) -> dict[str, int]:
        files_deleted = 0
        batches_cancelled = 0
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60

        try:
            files = await self.client.files.list(purpose="batch")
            for file in files.data:
                file_age = current_time - file.created_at
                if file_age > max_age_seconds:
                    try:
                        await self.client.files.delete(file.id)
                        logger.info(
                            f"Deleted old file: {file.id} (age: {file_age/86400:.1f} days)"
                        )
                        files_deleted += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete file {file.id}: {str(e)}")
        except Exception as e:
            logger.error(f"Error listing files: {str(e)}")

        try:
            batches = await self.client.batches.list(limit=100)
            for batch in batches.data:
                batch_age = current_time - batch.created_at
                can_cancel = batch.status in [
                    "completed",
                    "failed",
                    "expired",
                    "cancelled",
                ]
                if batch_age > max_age_seconds and can_cancel:
                    try:
                        await self.client.batches.cancel(batch.id)
                        logger.info(
                            f"Cancelled old batch: {batch.id} "
                            f"(age: {batch_age/86400:.1f} days)"
                        )
                        batches_cancelled += 1
                    except Exception as e:
                        if (
                            "already" not in str(e).lower()
                            and "cannot" not in str(e).lower()
                        ):
                            logger.warning(
                                f"Failed to cancel batch {batch.id}: {str(e)}"
                            )
        except Exception as e:
            logger.error(f"Error listing batches: {str(e)}")

        logger.info(
            f"Cleanup completed: {files_deleted} files deleted, "
            f"{batches_cancelled} batches cancelled"
        )
        return {"files_deleted": files_deleted, "batches_cancelled": batches_cancelled}

    def parse_jsonl_results(
        self, jsonl_file: str | bytes, model_name: str
    ) -> list[dict[str, Any]]:
        results = []
        content = (
            jsonl_file if isinstance(jsonl_file, bytes) else open(jsonl_file, "rb").read()
        )
        text = content.decode("utf-8", errors="replace")

        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                result = json.loads(line)
                if "response" in result and "body" in result["response"]:
                    try:
                        results.append(
                            {
                                "text": result["response"]["body"]["choices"][0]["message"][
                                    "content"
                                ],
                                "batch_id": result.get("custom_id", "").replace(
                                    "CALL_", ""
                                ),
                                "usage": {
                                    "input_tokens": result["response"]["body"]["usage"][
                                        "prompt_tokens"
                                    ],
                                    "output_tokens": result["response"]["body"]["usage"][
                                        "completion_tokens"
                                    ],
                                    "token_source": "batch-api",
                                },
                                "model": result["response"]["body"].get("model", model_name),
                            }
                        )
                    except Exception as e:
                        logger.error(f"Error parsing result content: {e}")
                        results.append(
                            {
                                "text": "error in getting content",
                                "batch_id": result.get("custom_id", "").replace(
                                    "CALL_", ""
                                ),
                                "usage": {
                                    "input_tokens": result["response"]["body"]["usage"][
                                        "prompt_tokens"
                                    ],
                                    "output_tokens": result["response"]["body"]["usage"][
                                        "completion_tokens"
                                    ],
                                    "token_source": "batch-api",
                                },
                                "model": result["response"]["body"].get("model", model_name),
                            }
                        )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSONL line: {e}")

        return results
