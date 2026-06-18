import logging
import threading

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver

from browser_service.config import (
    CHROME_BIN,
    CHROMEDRIVER_PATH,
    HEADLESS,
    PAGE_LOAD_TIMEOUT,
)

logger = logging.getLogger(__name__)


class BrowserManager:
    """Singleton Chrome session manager."""

    def __init__(self):
        self._driver: WebDriver | None = None
        self._lock = threading.Lock()

    def _build_options(self) -> Options:
        options = Options()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1280,800")
        options.add_argument("--lang=uk-UA")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        if CHROME_BIN:
            options.binary_location = CHROME_BIN

        return options

    def _build_service(self) -> Service | None:
        if CHROMEDRIVER_PATH:
            return Service(CHROMEDRIVER_PATH)
        return None

    def _is_alive(self) -> bool:
        if not self._driver:
            return False
        try:
            _ = self._driver.current_url
            return True
        except Exception:
            return False

    def _launch(self) -> WebDriver:
        self._cleanup()
        logger.info("Launching Chrome (headless=%s)", HEADLESS)
        self._driver = webdriver.Chrome(
            options=self._build_options(),
            service=self._build_service(),
        )
        self._driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        self._driver.implicitly_wait(0)
        return self._driver

    def _cleanup(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
        self._driver = None

    def get_driver(self, force_new: bool = False) -> WebDriver:
        with self._lock:
            if force_new or not self._is_alive():
                return self._launch()
            return self._driver  # type: ignore[return-value]

    def restart(self) -> WebDriver:
        with self._lock:
            return self._launch()

    def shutdown(self) -> None:
        with self._lock:
            self._cleanup()


_manager: BrowserManager | None = None
_manager_lock = threading.Lock()


def get_browser_manager() -> BrowserManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = BrowserManager()
        return _manager
