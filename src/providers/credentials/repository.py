"""Repository for model credentials with an in-process TTL cache.

Credentials are decrypted at read time via `pgp_sym_decrypt`, keyed by
`CREDENTIAL_ENCRYPTION_KEY`. The cache avoids hitting Postgres on every
provider call; invalidate it when credentials rotate.
"""
import logging
import time
from dataclasses import dataclass

from sqlalchemy import text

from providers.exceptions import CredentialNotFoundError
from shared.config import settings
from shared.db.session import get_session

logger = logging.getLogger(__name__)


@dataclass
class DecryptedCredential:
    provider: str
    model_name: str
    api_key: str
    api_endpoint: str | None = None
    api_version: str | None = None


class CredentialRepository:
    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, DecryptedCredential]] = {}

    async def get(self, model_name: str) -> DecryptedCredential:
        now = time.monotonic()
        cached = self._cache.get(model_name)
        if cached and (now - cached[0]) < self._ttl:
            return cached[1]

        credential = await self._fetch(model_name)
        self._cache[model_name] = (now, credential)
        return credential

    async def _fetch(self, model_name: str) -> DecryptedCredential:
        async with get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                        provider,
                        model_name,
                        pgp_sym_decrypt(api_key_enc, :key)::text AS api_key,
                        api_endpoint,
                        api_version
                    FROM model_credentials
                    WHERE model_name = :model_name AND is_active = true
                    """
                ),
                {
                    "key": settings.credential_encryption_key,
                    "model_name": model_name,
                },
            )
            row = result.mappings().first()

        if row is None:
            raise CredentialNotFoundError(
                f"No active credential for model '{model_name}'"
            )

        logger.info(f"Loaded credential for model '{model_name}'")
        return DecryptedCredential(
            provider=row["provider"],
            model_name=row["model_name"],
            api_key=row["api_key"],
            api_endpoint=row["api_endpoint"],
            api_version=row["api_version"],
        )

    def invalidate(self, model_name: str | None = None) -> None:
        if model_name is None:
            self._cache.clear()
        else:
            self._cache.pop(model_name, None)


_repository: CredentialRepository | None = None


def get_credential_repository() -> CredentialRepository:
    global _repository
    if _repository is None:
        _repository = CredentialRepository()
    return _repository
