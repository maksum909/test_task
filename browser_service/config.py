import os

TEMPAIL_URL = os.getenv("TEMPAIL_URL", "https://tempail.com/ua/")
PAGE_LOAD_TIMEOUT = int(os.getenv("PAGE_LOAD_TIMEOUT", "60"))
ELEMENT_TIMEOUT = int(os.getenv("ELEMENT_TIMEOUT", "30"))
MANUAL_CAPTCHA_TIMEOUT = int(os.getenv("MANUAL_CAPTCHA_TIMEOUT", "120"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
SERVICE_PORT = int(os.getenv("BROWSER_SERVICE_PORT", "5051"))

CHROME_BIN = os.getenv("CHROME_BIN")
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH")
