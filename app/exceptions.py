class TempailError(Exception):
    """Base error for tempail operations."""

    def __init__(self, message: str, code: str = "TEMPAIL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class PageLoadError(TempailError):
    def __init__(self, message: str = "Failed to load tempail page"):
        super().__init__(message, "PAGE_LOAD_ERROR")


class CaptchaBlockedError(TempailError):
    def __init__(self, message: str = "Blocked by bot protection, retry later"):
        super().__init__(message, "CAPTCHA_BLOCKED")


class SessionStaleError(TempailError):
    def __init__(self, message: str = "Browser session is stale"):
        super().__init__(message, "SESSION_STALE")


class EmailNotFoundError(TempailError):
    def __init__(self, email_id: str):
        super().__init__(f"Email with id '{email_id}' not found", "EMAIL_NOT_FOUND")


class BrowserCrashError(TempailError):
    def __init__(self, message: str = "Browser crashed or became unresponsive"):
        super().__init__(message, "BROWSER_CRASH")
