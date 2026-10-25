import re
from typing import Tuple

_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key\s*[:=]\s*)(['\"]?)[^\s'\"]+", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
)


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def redact_secrets(text: str) -> str:
    if not text:
        return ""
    redacted = str(text)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            redacted = pattern.sub(r"\1\2[redacted]", redacted)
        else:
            redacted = pattern.sub("[redacted]", redacted)
    return redacted


def classify_exception(exc: Exception, *, gemini_configured: bool) -> Tuple[str, str, int]:
    """Map an exception to (code, user_message, http_status) without leaking secrets."""
    if isinstance(exc, AppError):
        return exc.code, exc.message, exc.status_code

    raw = redact_secrets(str(exc) or exc.__class__.__name__)
    lowered = raw.lower()

    if not gemini_configured or "api key is required" in lowered:
        return (
            "missing_config",
            "Bill extraction is not configured on the server. Set GEMINI_API_KEY in the Vercel project environment variables.",
            503,
        )

    if isinstance(exc, FileNotFoundError) or "not found" in lowered and "bill image" in lowered:
        return ("not_found", "The bill image could not be found on the server. Please upload the file again.", 404)

    if "timeout" in lowered or "deadline" in lowered or "timed out" in lowered:
        return (
            "timeout",
            "The AI service took too long to respond. Try a smaller image, or retry the upload.",
            504,
        )

    if "429" in raw or "resource_exhausted" in lowered or "quota" in lowered or "rate limit" in lowered:
        return (
            "api_failure",
            "The AI service is rate-limited right now. Wait a moment and try again.",
            429,
        )

    if "401" in raw or "403" in raw or "permission" in lowered or "unauthenticated" in lowered or "invalid api key" in lowered:
        return (
            "api_failure",
            "The AI service rejected the server credentials. Check that GEMINI_API_KEY is valid.",
            502,
        )

    if "404" in raw and ("model" in lowered or "not found" in lowered):
        return (
            "api_failure",
            "The configured Gemini model is unavailable. Check MODEL_NAME in the server environment.",
            502,
        )

    if "json" in lowered and ("expecting" in lowered or "decode" in lowered or "parse" in lowered):
        return (
            "api_failure",
            "The AI service returned data that could not be parsed as billing JSON.",
            502,
        )

    if "empty response" in lowered:
        return ("api_failure", "The AI service returned an empty extraction result. Try a clearer bill image.", 502)

    return (
        "api_failure",
        "The AI service failed while reading this bill. Try another PNG or JPG image.",
        502,
    )
