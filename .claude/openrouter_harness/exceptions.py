from __future__ import annotations

from typing import Optional


class HarnessError(Exception):
    pass


class RetryableError(HarnessError):
    def __init__(
        self,
        message: str,
        reason: str,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


class NonRetryableError(HarnessError):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code


class TotalTimeoutError(HarnessError):
    def __init__(self, message: str, elapsed_s: float) -> None:
        super().__init__(message)
        self.elapsed_s = elapsed_s
