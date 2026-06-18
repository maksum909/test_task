import logging
import urllib.error
import urllib.request
import json

from app.config import BROWSER_SERVICE_URL
from app.exceptions import (
    BrowserCrashError,
    CaptchaBlockedError,
    EmailNotFoundError,
    PageLoadError,
    TempailError,
)

logger = logging.getLogger(__name__)

ERROR_MAP = {
    "PAGE_LOAD_ERROR": PageLoadError,
    "CAPTCHA_BLOCKED": CaptchaBlockedError,
    "EMAIL_NOT_FOUND": EmailNotFoundError,
    "BROWSER_CRASH": BrowserCrashError,
}


class BrowserClient:
    """HTTP client for the Selenium browser microservice."""

    def __init__(self, base_url: str = BROWSER_SERVICE_URL):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str) -> dict:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method=method)

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode()
            try:
                data = json.loads(body)
                code = data.get("code", "BROWSER_ERROR")
                message = data.get("error", body)
            except json.JSONDecodeError:
                code = "BROWSER_ERROR"
                message = body

            error_cls = ERROR_MAP.get(code, TempailError)
            raise error_cls(message) from exc
        except urllib.error.URLError as exc:
            logger.error("Browser service unreachable: %s", exc)
            raise BrowserCrashError(
                f"Browser service unavailable at {self.base_url}"
            ) from exc

    def get_current_email(self) -> str:
        data = self._request("GET", "/internal/email")
        return data["email"]

    def get_oturum(self) -> str | None:
        data = self._request("GET", "/internal/email")
        return data.get("oturum")

    def get_inbox(self) -> list[dict]:
        data = self._request("GET", "/internal/inbox")
        return data.get("emails", [])

    def get_email_content(self, email_id: str, inbox_item: dict | None = None) -> dict:
        return self._request("GET", f"/internal/email/{email_id}")

    def refresh_email(self) -> str:
        data = self._request("POST", "/internal/email/refresh")
        return data["email"]

    def health(self) -> dict:
        return self._request("GET", "/health")


_client: BrowserClient | None = None


def get_browser_client() -> BrowserClient:
    global _client
    if _client is None:
        _client = BrowserClient()
    return _client
