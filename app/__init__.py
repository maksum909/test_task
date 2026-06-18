from flask import Flask

from app.api.routes import api_bp
from app.exceptions import TempailError


def create_app() -> Flask:
    app = Flask(__name__)

    app.register_blueprint(api_bp)

    @app.errorhandler(TempailError)
    def handle_tempail_error(error: TempailError):
        status = 503
        if error.code == "EMAIL_NOT_FOUND":
            status = 404
        elif error.code == "CAPTCHA_BLOCKED":
            status = 429
        return {"error": error.message, "code": error.code}, status

    @app.errorhandler(Exception)
    def handle_generic_error(error: Exception):
        return {"error": str(error), "code": "INTERNAL_ERROR"}, 500

    return app
