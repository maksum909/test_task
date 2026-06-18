class BrowserServiceError(Exception):
    def __init__(self, message: str, code: str = "BROWSER_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class PageLoadError(BrowserServiceError):
    def __init__(self, message: str = "Failed to load tempail page"):
        super().__init__(message, "PAGE_LOAD_ERROR")


class CaptchaBlockedError(BrowserServiceError):
    def __init__(self, message: str = "Blocked by bot protection, retry later"):
        super().__init__(message, "CAPTCHA_BLOCKED")


class EmailNotFoundError(BrowserServiceError):
    def __init__(self, email_id: str):
        super().__init__(f"Email with id '{email_id}' not found", "EMAIL_NOT_FOUND")


class BrowserCrashError(BrowserServiceError):
    def __init__(self, message: str = "Browser crashed or became unresponsive"):
        super().__init__(message, "BROWSER_CRASH")
