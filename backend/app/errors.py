"""Structured errors so the UI can show a clear message + a next step."""
from __future__ import annotations

from typing import Optional


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        hint: Optional[str] = None,
        status: int = 400,
        stage: Optional[str] = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status = status
        self.stage = stage

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "stage": self.stage,
        }


class Cancelled(Exception):
    """Raised inside the pipeline when the user cancels a job."""
