"""Human-friendly references (Crockford base32: no I, L, O, U to avoid misreading)."""

from __future__ import annotations

import secrets

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_reference(prefix: str, length: int = 6) -> str:
    return f"{prefix}-" + "".join(secrets.choice(_ALPHABET) for _ in range(length))
