import hashlib
import logging
import time

from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from browser_service.browser import BrowserManager, get_browser_manager
from browser_service.config import (
    ELEMENT_TIMEOUT,
    HEADLESS,
    MANUAL_CAPTCHA_TIMEOUT,
    MAX_RETRIES,
    PAGE_LOAD_TIMEOUT,
    TEMPAIL_URL,
)
from browser_service.exceptions import (
    BrowserCrashError,
    CaptchaBlockedError,
    EmailNotFoundError,
    PageLoadError,
)

logger = logging.getLogger(__name__)

SELECTORS = {
    "email_input": (By.ID, "eposta_adres"),
    "cookie_accept": (By.ID, "cerezKabul"),
    "inbox_rows": (By.CSS_SELECTOR, "ul.mailler > li:not(.baslik)"),
    "refresh_link": (By.CSS_SELECTOR, "a.yenile-link"),
    "new_email_link": (By.CSS_SELECTOR, "a.yoket-link"),
    "waiting_state": (By.CSS_SELECTOR, ".eposta-bekleniyor"),
    "sender": (By.CSS_SELECTOR, ".gonderen"),
    "subject": (By.CSS_SELECTOR, ".baslik"),
    "timestamp": (By.CSS_SELECTOR, ".zaman"),
}

BODY_SELECTORS = [
    ".mail-icerik",
    ".eposta-icerik",
    ".mail-body",
    "#mail-icerik",
    ".icerik",
    ".mail-detay",
    ".eposta-detay",
    ".mail-oku",
]


class TempailScraper:
    """Automates tempail.com via Selenium Chrome."""

    def __init__(self, browser_manager: BrowserManager | None = None):
        self._browser = browser_manager or get_browser_manager()

    def _wait(self, driver: WebDriver) -> WebDriverWait:
        return WebDriverWait(driver, ELEMENT_TIMEOUT)

    def _sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _dismiss_cookies(self, driver: WebDriver) -> None:
        try:
            btn = driver.find_element(*SELECTORS["cookie_accept"])
            if btn.is_displayed():
                btn.click()
                self._sleep(0.5)
        except NoSuchElementException:
            pass

    def _is_captcha_page(self, driver: WebDriver) -> bool:
        title = driver.title.lower()
        source = driver.page_source[:3000].lower()
        return (
            "verifying" in title
            or "captcha" in source
            or "recaptcha" in source
            or "bot-kontrol" in source
            or "not a robot" in source
        )

    def _email_ready(self, driver: WebDriver) -> str | None:
        try:
            value = driver.find_element(*SELECTORS["email_input"]).get_attribute("value")
            return value if value and "@" in value else None
        except NoSuchElementException:
            return None

    def _wait_for_manual_captcha(self, driver: WebDriver) -> bool:
        if HEADLESS:
            logger.error(
                "CAPTCHA detected in headless mode. Docker has no display — "
                "a Chrome window cannot open. Run the browser service on the "
                "host with HEADLESS=false, or use: docker compose -f docker-compose.dev.yml up"
            )
            return False

        logger.warning(
            "CAPTCHA detected — solve it in the Chrome window (up to %ss)",
            MANUAL_CAPTCHA_TIMEOUT,
        )
        deadline = time.time() + MANUAL_CAPTCHA_TIMEOUT
        while time.time() < deadline:
            email = self._email_ready(driver)
            if email:
                logger.info("Challenge cleared — email visible: %s", email)
                return True
            if not self._is_captcha_page(driver) and self._email_ready(driver):
                return True
            self._sleep(2)
        return False

    def _wait_for_email(self, driver: WebDriver) -> None:
        if self._is_captcha_page(driver):
            if not self._wait_for_manual_captcha(driver):
                raise CaptchaBlockedError()
            return

        wait = self._wait(driver)
        wait.until(EC.visibility_of_element_located(SELECTORS["email_input"]))
        wait.until(lambda d: self._email_ready(d) is not None)

    def _navigate(self, force_new: bool = False) -> str:
        last_error: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                driver = (
                    self._browser.restart()
                    if attempt > 0
                    else self._browser.get_driver(force_new=force_new)
                )
                driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
                driver.get(TEMPAIL_URL)
                self._sleep(3 + attempt)

                self._wait_for_email(driver)
                self._dismiss_cookies(driver)
                email = self._email_ready(driver)
                if not email:
                    raise PageLoadError("Email input empty after page load")
                return email

            except CaptchaBlockedError:
                last_error = CaptchaBlockedError()
                logger.warning("Captcha blocked on attempt %d", attempt + 1)
                self._sleep(2 * (attempt + 1))
            except Exception as exc:
                last_error = exc
                logger.warning("Navigation failed on attempt %d: %s", attempt + 1, exc)
                self._sleep(1 * (attempt + 1))

        if isinstance(last_error, CaptchaBlockedError):
            raise last_error
        raise PageLoadError(str(last_error) if last_error else "Unknown navigation error")

    def _ensure_driver(self) -> WebDriver:
        try:
            driver = self._browser.get_driver()
            if self._email_ready(driver):
                return driver
        except Exception:
            pass
        self._navigate(force_new=True)
        return self._browser.get_driver()

    def get_current_email(self) -> str:
        driver = self._ensure_driver()
        try:
            email = self._email_ready(driver)
            if not email:
                return self._navigate()
            return email
        except WebDriverException as exc:
            logger.error("Failed to get current email: %s", exc)
            raise BrowserCrashError(str(exc)) from exc

    def refresh_email(self) -> str:
        driver = self._ensure_driver()
        try:
            driver.find_element(*SELECTORS["new_email_link"]).click()
            self._sleep(3)
            self._wait_for_email(driver)
            email = self._email_ready(driver)
            if not email:
                raise PageLoadError("Email empty after refresh")
            return email
        except CaptchaBlockedError:
            raise
        except Exception as exc:
            logger.warning("Refresh via click failed, re-navigating: %s", exc)
            return self._navigate(force_new=True)

    def _parse_inbox_rows(self, driver: WebDriver) -> list[dict]:
        emails = []
        rows = driver.find_elements(*SELECTORS["inbox_rows"])

        for row in rows:
            try:
                row.find_element(*SELECTORS["waiting_state"])
                continue
            except NoSuchElementException:
                pass

            sender = self._safe_text(row, SELECTORS["sender"])
            subject = self._safe_text(row, SELECTORS["subject"])
            timestamp = self._safe_text(row, SELECTORS["timestamp"])

            if not sender and not subject:
                continue

            row_id = row.get_attribute("data-id") or row.get_attribute("id")
            if not row_id:
                row_id = hashlib.md5(
                    f"{sender}|{subject}|{timestamp}".encode()
                ).hexdigest()[:12]

            emails.append(
                {
                    "id": row_id,
                    "sender": sender,
                    "subject": subject,
                    "time": timestamp,
                }
            )

        return emails

    def _safe_text(self, parent, locator) -> str:
        try:
            return parent.find_element(*locator).text.strip()
        except NoSuchElementException:
            return ""

    def _refresh_inbox(self, driver: WebDriver) -> None:
        try:
            link = driver.find_element(*SELECTORS["refresh_link"])
            if link.is_displayed():
                link.click()
                self._sleep(3)
        except Exception as exc:
            logger.warning("Inbox refresh click failed: %s", exc)

    def get_inbox(self) -> list[dict]:
        driver = self._ensure_driver()
        try:
            self._refresh_inbox(driver)
            return self._parse_inbox_rows(driver)
        except WebDriverException as exc:
            logger.error("Failed to get inbox: %s", exc)
            raise BrowserCrashError(str(exc)) from exc

    def _extract_body(self, driver: WebDriver) -> str:
        for selector in BODY_SELECTORS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                text = el.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue

        try:
            iframe = driver.find_element(By.TAG_NAME, "iframe")
            driver.switch_to.frame(iframe)
            body = driver.find_element(By.TAG_NAME, "body").text.strip()
            driver.switch_to.default_content()
            return body
        except NoSuchElementException:
            pass

        return ""

    def get_email_content(self, email_id: str, inbox_item: dict | None = None) -> dict:
        driver = self._ensure_driver()
        try:
            self._refresh_inbox(driver)
            rows = driver.find_elements(*SELECTORS["inbox_rows"])
            target_row = None

            for row in rows:
                try:
                    row.find_element(*SELECTORS["waiting_state"])
                    continue
                except NoSuchElementException:
                    pass

                sender = self._safe_text(row, SELECTORS["sender"])
                subject = self._safe_text(row, SELECTORS["subject"])
                timestamp = self._safe_text(row, SELECTORS["timestamp"])

                row_id = row.get_attribute("data-id") or row.get_attribute("id")
                if not row_id:
                    row_id = hashlib.md5(
                        f"{sender}|{subject}|{timestamp}".encode()
                    ).hexdigest()[:12]

                if row_id == email_id:
                    target_row = row
                    inbox_item = inbox_item or {
                        "id": row_id,
                        "sender": sender,
                        "subject": subject,
                        "time": timestamp,
                    }
                    break

                if inbox_item and (
                    sender == inbox_item.get("sender")
                    and subject == inbox_item.get("subject")
                ):
                    target_row = row
                    break

            if not target_row:
                raise EmailNotFoundError(email_id)

            target_row.click()
            self._sleep(2)

            body = self._extract_body(driver)
            if not body:
                try:
                    container = driver.find_element(
                        By.CSS_SELECTOR, ".mail-alani, #epostalar, .ana-konteyner"
                    )
                    body = container.text.strip()
                except NoSuchElementException:
                    body = ""

            return {
                "id": email_id,
                "sender": inbox_item.get("sender", "") if inbox_item else "",
                "subject": inbox_item.get("subject", "") if inbox_item else "",
                "time": inbox_item.get("time", "") if inbox_item else "",
                "body": body,
            }
        except EmailNotFoundError:
            raise
        except WebDriverException as exc:
            logger.error("Failed to get email content: %s", exc)
            raise BrowserCrashError(str(exc)) from exc

    def get_oturum(self) -> str | None:
        driver = self._ensure_driver()
        try:
            return driver.execute_script(
                "return (typeof oturum !== 'undefined' ? oturum : null);"
            )
        except WebDriverException:
            return None


_scraper: TempailScraper | None = None


def get_scraper() -> TempailScraper:
    global _scraper
    if _scraper is None:
        _scraper = TempailScraper()
    return _scraper
