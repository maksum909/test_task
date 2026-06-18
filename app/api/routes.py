import logging

from flask import Blueprint, jsonify

from app.exceptions import EmailNotFoundError, TempailError
from app.services.redis_store import get_redis_store
from app.services.browser_client import get_browser_client

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _success(data: dict, status: int = 200):
    return jsonify(data), status


@api_bp.route("/email", methods=["GET"])
def get_email():
    client = get_browser_client()
    store = get_redis_store()

    email = client.get_current_email()
    oturum = client.get_oturum()
    store.save_session(email, oturum)

    return _success({"email": email})


@api_bp.route("/inbox", methods=["GET"])
def get_inbox():
    client = get_browser_client()
    store = get_redis_store()

    emails = client.get_inbox()

    stored_emails = []
    for item in emails:
        email_id = store.save_email(
            {
                "id": item["id"],
                "sender": item["sender"],
                "subject": item["subject"],
                "time": item["time"],
            }
        )
        stored_emails.append(
            {
                "id": email_id,
                "sender": item["sender"],
                "subject": item["subject"],
                "time": item["time"],
            }
        )

    store.save_inbox(stored_emails)

    return _success({"emails": stored_emails, "count": len(stored_emails)})


@api_bp.route("/email/refresh", methods=["POST"])
def refresh_email():
    client = get_browser_client()
    store = get_redis_store()

    store.clear_emails()
    new_email = client.refresh_email()
    oturum = client.get_oturum()
    store.save_session(new_email, oturum)

    return _success({"email": new_email, "message": "New temporary email generated"})


@api_bp.route("/email/<email_id>", methods=["GET"])
def get_email_by_id(email_id: str):
    store = get_redis_store()
    client = get_browser_client()

    cached = store.get_email(email_id)
    if cached and cached.get("body"):
        return _success(cached)

    inbox_item = cached
    if not inbox_item:
        inbox = store.get_inbox()
        inbox_item = next((e for e in inbox if e["id"] == email_id), None)

    if not inbox_item:
        inbox_data = client.get_inbox()
        inbox_item = next((e for e in inbox_data if e["id"] == email_id), None)

    if not inbox_item:
        raise EmailNotFoundError(email_id)

    try:
        full_email = client.get_email_content(email_id, inbox_item)
    except Exception:
        raise EmailNotFoundError(email_id) from None

    store.save_email(full_email)
    return _success(full_email)


@api_bp.route("/health", methods=["GET"])
def health():
    store = get_redis_store()
    redis_ok = False
    browser_ok = False

    try:
        redis_ok = store.ping()
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)

    try:
        get_browser_client().health()
        browser_ok = True
    except Exception as exc:
        logger.warning("Browser service health check failed: %s", exc)

    status = "ok" if redis_ok and browser_ok else "degraded"
    return _success(
        {
            "status": status,
            "redis": "connected" if redis_ok else "disconnected",
            "browser_service": "connected" if browser_ok else "disconnected",
        }
    )
