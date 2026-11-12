"""Groq client factory + one retry wrapper that turns SDK exceptions into AppErrors."""
from __future__ import annotations

import random
import time
from typing import Callable, Optional, TypeVar

import groq
from groq import Groq

from .errors import AppError, Cancelled

T = TypeVar("T")

MAX_RATE_LIMIT_WAIT = 75  # seconds we are willing to sleep for one 429


def make_client(api_key: str, timeout: float) -> Groq:
    # max_retries=0: we do our own retries so the UI can show what is happening.
    return Groq(api_key=api_key, timeout=timeout, max_retries=0)


def _message(e: Exception) -> str:
    msg = getattr(e, "message", None) or str(e)
    body = getattr(e, "body", None)
    if isinstance(body, dict):
        inner = body.get("error", body)
        if isinstance(inner, dict) and inner.get("message"):
            msg = inner["message"]
    return str(msg)


def _retry_after(e: Exception) -> Optional[float]:
    resp = getattr(e, "response", None)
    if resp is None:
        return None
    raw = resp.headers.get("retry-after")
    try:
        return float(raw) if raw is not None else None
    except ValueError:
        return None


def call_with_retry(
    fn: Callable[[], T],
    *,
    retries: int,
    stage: str,
    cancel: Optional[Callable[[], None]] = None,
    on_wait: Optional[Callable[[str], None]] = None,
) -> T:
    """Run fn(); retry transient failures; raise AppError for everything else."""
    attempt = 0
    while True:
        if cancel:
            cancel()
        try:
            return fn()

        except groq.AuthenticationError as e:
            raise AppError(
                "INVALID_API_KEY", "Groq rejected your API key.",
                "Open Settings, paste a fresh key from console.groq.com/keys and press Test key.",
                401, stage) from e

        except groq.PermissionDeniedError as e:
            raise AppError(
                "PERMISSION_DENIED", f"Groq refused the request: {_message(e)}",
                "Your key or organization may not have access to this model/region. "
                "Pick another model in Settings.", 403, stage) from e

        except groq.NotFoundError as e:
            raise AppError(
                "MODEL_NOT_FOUND", f"Model not found: {_message(e)}",
                "The model may have been renamed or retired. Press 'Refresh models' in Settings "
                "and choose one from the live list.", 404, stage) from e

        except groq.BadRequestError as e:
            msg = _message(e)
            low = msg.lower()
            body = getattr(e, "body", None)
            inner = body.get("error", body) if isinstance(body, dict) else {}
            code = str(inner.get("code", "")) if isinstance(inner, dict) else ""
            if (code == "json_validate_failed" or "json_validate_failed" in low
                    or "failed to generate json" in low or "failed to validate json" in low):
                raise AppError("LLM_JSON_INVALID", msg, None, 422, stage) from e
            if "decommission" in low or "no longer supported" in low or "does not exist" in low:
                raise AppError(
                    "MODEL_NOT_FOUND", f"The selected model is unavailable: {msg}",
                    "Press 'Refresh models' in Settings and pick another one.", 400, stage) from e
            raise AppError("BAD_REQUEST", f"Groq said: {msg}", None, 400, stage) from e

        except groq.RateLimitError as e:
            wait = _retry_after(e)
            msg = _message(e)
            if wait is not None and wait > MAX_RATE_LIMIT_WAIT:
                mins = int(wait // 60) + 1
                raise AppError(
                    "RATE_LIMITED",
                    f"Groq rate limit reached (about {mins} min until it resets). {msg}",
                    "This looks like a daily/hourly cap. Wait, or switch to a different model in "
                    "Settings (each model has its own limit).", 429, stage) from e
            if attempt >= retries:
                raise AppError(
                    "RATE_LIMITED", f"Groq rate limit reached. {msg}",
                    "Wait a minute and retry, or switch model in Settings.", 429, stage) from e
            delay = wait if wait is not None else 2.0 * (2 ** attempt)
            delay = min(delay + random.random(), MAX_RATE_LIMIT_WAIT)
            if on_wait:
                on_wait(f"Rate limited by Groq, retrying in {int(delay) + 1}s…")
            time.sleep(delay)
            attempt += 1

        except (groq.APITimeoutError, groq.APIConnectionError) as e:
            timed_out = isinstance(e, groq.APITimeoutError)
            if attempt >= retries:
                if timed_out:
                    raise AppError(
                        "TIMEOUT", "Groq took too long to respond.",
                        "Increase 'Request timeout' in Settings, or retry.", 504, stage) from e
                raise AppError(
                    "NETWORK_ERROR", "Could not reach Groq.",
                    "Check your internet connection / VPN / firewall and retry.", 502, stage) from e
            delay = 1.5 * (2 ** attempt) + random.random()
            if on_wait:
                on_wait(f"Network hiccup, retrying in {int(delay) + 1}s…")
            time.sleep(delay)
            attempt += 1

        except groq.APIStatusError as e:  # 4xx/5xx not handled above
            code = getattr(e, "status_code", 0)
            if code == 413:
                raise AppError(
                    "PAYLOAD_TOO_LARGE", "Groq says the audio chunk is too large.",
                    "Lower 'Chunk length' in Settings (e.g. 300 s) or use MP3 format.", 413, stage) from e
            if code >= 500 and attempt < retries:
                delay = 1.5 * (2 ** attempt) + random.random()
                if on_wait:
                    on_wait(f"Groq server error ({code}), retrying in {int(delay) + 1}s…")
                time.sleep(delay)
                attempt += 1
                continue
            raise AppError(
                "GROQ_ERROR", f"Groq error {code}: {_message(e)}",
                "If this keeps happening check status.groq.com.", 502, stage) from e

        except Cancelled:
            raise
