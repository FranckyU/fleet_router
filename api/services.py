import logging
import requests
from django.conf import settings
from requests.exceptions import RequestException, Timeout

logger = logging.getLogger(__name__)


class ExternalAPIError(Exception):
    """Raised when the external API call fails."""


class ExternalAPIClient:
    """
    Generic HTTP client for the external API.

    The base URL and timeout come from settings so they can be configured
    via environment variables once the target API is known.
    """

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or settings.EXTERNAL_API_BASE_URL or "").rstrip("/")
        self.timeout = timeout or settings.EXTERNAL_API_TIMEOUT

    def get(self, path: str, params: dict | None = None) -> dict | list:
        if not self.base_url:
            raise ExternalAPIError("EXTERNAL_API_BASE_URL is not configured")

        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Timeout as exc:
            logger.warning("Timeout calling %s", url)
            raise ExternalAPIError(f"Timeout calling {url}") from exc
        except RequestException as exc:
            logger.exception("External API error for %s", url)
            raise ExternalAPIError(str(exc)) from exc
