import logging

from browser_service.app import create_browser_app
from browser_service.config import SERVICE_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = create_browser_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=SERVICE_PORT, debug=False, threaded=False)
