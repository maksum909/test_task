import json
import logging
import threading
import uuid
from typing import Any

import redis

from app.config import EMAIL_CACHE_TTL, REDIS_URL

logger = logging.getLogger(__name__)

SESSION_KEY = "tempail:session"
EMAIL_KEY_PREFIX = "tempail:email:"
INBOX_KEY = "tempail:inbox"


class RedisStore:
    def __init__(self, url: str = REDIS_URL):
        self._client = redis.from_url(url, decode_responses=True)

    def ping(self) -> bool:
        return self._client.ping()

    def save_session(self, email: str, oturum: str | None = None) -> None:
        data = {"email": email, "oturum": oturum}
        self._client.set(SESSION_KEY, json.dumps(data))

    def get_session(self) -> dict[str, Any] | None:
        raw = self._client.get(SESSION_KEY)
        if not raw:
            return None
        return json.loads(raw)

    def save_email(self, email_data: dict[str, Any]) -> str:
        email_id = email_data.get("id") or str(uuid.uuid4())
        email_data["id"] = email_id
        self._client.setex(
            f"{EMAIL_KEY_PREFIX}{email_id}",
            EMAIL_CACHE_TTL,
            json.dumps(email_data),
        )
        return email_id

    def get_email(self, email_id: str) -> dict[str, Any] | None:
        raw = self._client.get(f"{EMAIL_KEY_PREFIX}{email_id}")
        if not raw:
            return None
        return json.loads(raw)

    def save_inbox(self, emails: list[dict[str, Any]]) -> None:
        self._client.setex(INBOX_KEY, EMAIL_CACHE_TTL, json.dumps(emails))

    def get_inbox(self) -> list[dict[str, Any]]:
        raw = self._client.get(INBOX_KEY)
        if not raw:
            return []
        return json.loads(raw)

    def clear_emails(self) -> None:
        inbox = self.get_inbox()
        for item in inbox:
            self._client.delete(f"{EMAIL_KEY_PREFIX}{item['id']}")
        self._client.delete(INBOX_KEY)


_store: RedisStore | None = None
_store_lock = threading.Lock()


def get_redis_store() -> RedisStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = RedisStore()
        return _store
