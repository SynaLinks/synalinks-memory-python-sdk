"""Exception hierarchy for the Synalinks Memory SDK."""

from typing import Optional


class SynalinksError(Exception):
    """Base exception for all Synalinks API errors."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[{status_code}] {code}: {message}")


class AuthenticationError(SynalinksError):
    """Raised on 401 Unauthorized."""

    def __init__(self, code: str = "unauthorized", message: str = "Invalid API key") -> None:
        super().__init__(401, code, message)


class ForbiddenError(SynalinksError):
    """Raised on 403 Forbidden."""

    def __init__(self, code: str = "forbidden", message: str = "Access denied") -> None:
        super().__init__(403, code, message)


class NotFoundError(SynalinksError):
    """Raised on 404 Not Found."""

    def __init__(self, code: str = "not_found", message: str = "Resource not found") -> None:
        super().__init__(404, code, message)


class RateLimitError(SynalinksError):
    """Raised on 429 Too Many Requests."""

    def __init__(
        self,
        code: str = "rate_limit_exceeded",
        message: str = "Rate limit exceeded",
        retry_after: Optional[float] = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(429, code, message)


class ValidationError(SynalinksError):
    """Raised on 400 Bad Request."""

    def __init__(self, code: str = "validation_error", message: str = "Bad request") -> None:
        super().__init__(400, code, message)
