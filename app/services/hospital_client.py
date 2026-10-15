"""Asynchronous HTTP client for interacting with the external Hospital Directory API."""

import asyncio
import logging
import random
from typing import Any, Dict, List, Optional
import httpx

from app.config import Settings, get_settings
from app.models.hospital import HospitalCreate, HospitalResponse

logger = logging.getLogger(__name__)


class UpstreamApiException(Exception):
    """Exception raised when an upstream Hospital Directory API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class HospitalClient:
    """Resilient async HTTP client for the Hospital Directory API."""

    def __init__(self, settings: Optional[Settings] = None, client: Optional[httpx.AsyncClient] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.HOSPITAL_API_BASE_URL.rstrip("/")
        self._external_client = client
        self._internal_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Provide managed async client with connection pooling."""
        if self._external_client is not None:
            return self._external_client

        if self._internal_client is None or self._internal_client.is_closed:
            limits = httpx.Limits(
                max_connections=self.settings.MAX_CONNECTIONS,
                max_keepalive_connections=self.settings.MAX_KEEPALIVE_CONNECTIONS,
                keepalive_expiry=30.0,
            )
            timeout = httpx.Timeout(
                timeout=self.settings.REQUEST_TIMEOUT_SECONDS,
                connect=5.0,
            )
            self._internal_client = httpx.AsyncClient(
                base_url=self.base_url,
                limits=limits,
                timeout=timeout,
                headers={"User-Agent": f"ParibusHPS/{self.settings.APP_VERSION}"},
            )
        return self._internal_client

    async def close(self):
        """Close internal HTTP client connections."""
        if self._internal_client and not self._internal_client.is_closed:
            await self._internal_client.aclose()

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        expected_status: int = 200,
    ) -> httpx.Response:
        """Execute HTTP request with exponential backoff and jitter for transient errors."""
        client = await self._get_client()
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        retries = self.settings.MAX_RETRIES

        for attempt in range(1, retries + 1):
            try:
                response = await client.request(method, url, json=json_data)

                # Return on expected success
                if response.status_code == expected_status:
                    return response

                # Non-retryable client errors (400, 422, etc.)
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    error_detail = response.text
                    try:
                        error_detail = response.json()
                    except Exception:
                        pass
                    raise UpstreamApiException(
                        message=f"Upstream API rejected request with HTTP {response.status_code}: {error_detail}",
                        status_code=response.status_code,
                        details=error_detail,
                    )

                # Transient server error or rate limit (5xx or 429) -> retry
                if attempt == retries:
                    raise UpstreamApiException(
                        message=f"Upstream API returned HTTP {response.status_code} after {retries} attempts: {response.text}",
                        status_code=response.status_code,
                    )

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                if attempt == retries:
                    raise UpstreamApiException(
                        message=f"Network error connecting to upstream API after {retries} attempts: {str(exc)}",
                        status_code=503,
                    ) from exc

            # Exponential backoff with full jitter
            delay = (self.settings.RETRY_BACKOFF_BASE * (2 ** (attempt - 1))) + random.uniform(0.05, 0.2)
            logger.warning(
                "Upstream request %s %s failed on attempt %d/%d. Retrying in %.2fs...",
                method, path, attempt, retries, delay
            )
            await asyncio.sleep(delay)

        raise UpstreamApiException("Unexpected failure during upstream request retry loop.")

    async def create_hospital(self, hospital_data: HospitalCreate) -> HospitalResponse:
        """Create a single hospital record with creation_batch_id."""
        payload = hospital_data.model_dump(exclude_none=True)
        response = await self._request_with_retry(
            method="POST",
            path="/hospitals/",
            json_data=payload,
            expected_status=200,
        )
        data = response.json()
        return HospitalResponse(**data)

    async def get_hospitals_by_batch(self, batch_id: str) -> List[HospitalResponse]:
        """Fetch all hospitals associated with a specific batch ID."""
        response = await self._request_with_retry(
            method="GET",
            path=f"/hospitals/batch/{batch_id}",
            expected_status=200,
        )
        data = response.json()
        if isinstance(data, list):
            return [HospitalResponse(**item) for item in data]
        return []

    async def activate_batch(self, batch_id: str) -> Dict[str, Any]:
        """Activate all hospitals in a batch simultaneously."""
        response = await self._request_with_retry(
            method="PATCH",
            path=f"/hospitals/batch/{batch_id}/activate",
            expected_status=200,
        )
        return response.json()

    async def delete_batch(self, batch_id: str) -> Dict[str, Any]:
        """Rollback/delete all hospitals created with the given batch ID."""
        response = await self._request_with_retry(
            method="DELETE",
            path=f"/hospitals/batch/{batch_id}",
            expected_status=200,
        )
        try:
            return response.json()
        except Exception:
            return {"deleted_count": 0, "message": "Batch deleted"}

    async def check_health(self) -> bool:
        """Verify upstream API health status."""
        try:
            client = await self._get_client()
            # Allow up to 25s to handle Render free-tier cold-start wakeups
            resp = await client.get("/", timeout=25.0)
            return resp.status_code in (200, 204, 301, 302, 307, 308)
        except Exception as exc:
            logger.warning("Health check to upstream API failed: %s", exc)
            return False

