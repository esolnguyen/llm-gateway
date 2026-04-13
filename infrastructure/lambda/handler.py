"""AWS Lambda entrypoint that invokes llm-wrapper behind an HTTP API.

Cold start:
  1. Fetch DB credentials + encryption key from Secrets Manager
  2. Export DATABASE_URL + CREDENTIAL_ENCRYPTION_KEY so the library's settings
     pick them up on first import
  3. Import the library and register cost handlers once

Per invocation:
  - Build an LLMService scoped to the caller's user/org from the request body
  - Run call_llm, then drain background cost-handler tasks before returning
    (the in-memory event bus spawns them via create_task; if we don't await
    them the Lambda freezes mid-flight and cost rows get lost)
"""
import asyncio
import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_sm = boto3.client("secretsmanager")


def _bootstrap_env() -> None:
    db_secret = json.loads(
        _sm.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    )
    encryption_key = _sm.get_secret_value(
        SecretId=os.environ["ENCRYPTION_KEY_SECRET_ARN"]
    )["SecretString"]

    os.environ["DATABASE_URL"] = (
        f"postgresql+asyncpg://{db_secret['username']}:{db_secret['password']}"
        f"@{db_secret['host']}:{db_secret['port']}/{db_secret.get('dbname', 'llm_wrapper')}"
    )
    os.environ["CREDENTIAL_ENCRYPTION_KEY"] = encryption_key


_bootstrap_env()

from costs import register_cost_handlers  # noqa: E402
from providers import LLMService, OrganisationInfo, UserInfo  # noqa: E402

register_cost_handlers()

_MODULE_NAME = os.environ.get("MODULE_NAME", "lambda")
_SERVICE_NAME = os.environ.get("SERVICE_NAME", "chat")


async def _process(body: dict) -> dict:
    user = body.get("user") or {}
    org = body.get("organisation") or {}

    service = LLMService(
        module_name=_MODULE_NAME,
        service_name=_SERVICE_NAME,
        user_info=UserInfo(
            id=user.get("id", "anonymous"),
            email=user.get("email", ""),
            status="active",
        ),
        organisation_info=OrganisationInfo(
            id=org.get("id", "default"),
            name=org.get("name", ""),
            status="active",
            type=org.get("type", "standard"),
        ),
    )

    response = await service.call_llm(
        model_name=body["model"],
        prompt=body["prompt"],
        external_ref_type=body.get("external_ref_type"),
        external_ref_id=body.get("external_ref_id"),
        event_metadata=body.get("metadata"),
    )

    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    return {
        "content": response.content,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
        if "model" not in body or "prompt" not in body:
            return _json(400, {"error": "model and prompt are required"})

        result = asyncio.run(_process(body))
        return _json(200, result)
    except KeyError as e:
        return _json(400, {"error": f"missing field: {e.args[0]}"})
    except Exception as e:
        logger.exception("llm invocation failed")
        return _json(500, {"error": str(e)})


def _json(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }
