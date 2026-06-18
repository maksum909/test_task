import logging

from flask import Flask, jsonify

from browser_service.exceptions import BrowserServiceError
from browser_service.tempail import get_scraper

logger = logging.getLogger(__name__)


def create_browser_app() -> Flask:
    app = Flask(__name__)

    @app.errorhandler(BrowserServiceError)
    def handle_browser_error(error: BrowserServiceError):
        status = 503
        if error.code == "EMAIL_NOT_FOUND":
            status = 404
        elif error.code == "CAPTCHA_BLOCKED":
            status = 429
        return jsonify({"error": error.message, "code": error.code}), status

    @app.errorhandler(Exception)
    def handle_generic_error(error: Exception):
        logger.exception("Unhandled error in browser service")
        return jsonify({"error": str(error), "code": "INTERNAL_ERROR"}), 500

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "browser"})

    @app.route("/internal/email", methods=["GET"])
    def get_email():
        scraper = get_scraper()
        email = scraper.get_current_email()
        oturum = scraper.get_oturum()
        return jsonify({"email": email, "oturum": oturum})

    @app.route("/internal/inbox", methods=["GET"])
    def get_inbox():
        scraper = get_scraper()
        emails = scraper.get_inbox()
        return jsonify({"emails": emails, "count": len(emails)})

    @app.route("/internal/email/<email_id>", methods=["GET"])
    def get_email_by_id(email_id: str):
        scraper = get_scraper()
        email = scraper.get_email_content(email_id)
        return jsonify(email)

    @app.route("/internal/email/refresh", methods=["POST"])
    def refresh_email():
        scraper = get_scraper()
        new_email = scraper.refresh_email()
        oturum = scraper.get_oturum()
        return jsonify(
            {
                "email": new_email,
                "oturum": oturum,
                "message": "New temporary email generated",
            }
        )

    return app
