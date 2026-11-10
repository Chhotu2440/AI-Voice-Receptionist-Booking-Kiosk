"""Indian mobile number normalization (E.164). Spoken-number parsing for the voice agent comes later."""

from __future__ import annotations

import re

from app.core.exceptions import ValidationFailed

_SEPARATORS = re.compile(r"[\s\-().]")
_MOBILE = re.compile(r"^[6-9]\d{9}$")


def normalize_indian_mobile(raw: str) -> str:
    """'+91 98765-43210', '09876543210', '919876543210' -> '+919876543210'."""
    digits = _SEPARATORS.sub("", raw or "")
    if digits.startswith("+91"):
        digits = digits[3:]
    elif digits.startswith("0091"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _MOBILE.match(digits):
        raise ValidationFailed(
            "Please enter a valid 10-digit Indian mobile number.", details={"field": "phone"}
        )
    return f"+91{digits}"


def mask_phone(e164: str) -> str:
    """+919876543210 -> 98•••••210 (for public screens and logs)."""
    local = e164[-10:]
    return f"{local[:2]}•••••{local[-3:]}"
