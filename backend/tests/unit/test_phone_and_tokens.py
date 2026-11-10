from __future__ import annotations

import uuid

import pytest

from app.core.exceptions import ValidationFailed
from app.services.phone import mask_phone, normalize_indian_mobile
from app.services.refs import new_reference
from app.services.tokens import make_token, verify_token
from tests.conftest import make_settings


@pytest.mark.parametrize(
    "raw",
    [
        "9876543210",
        "+91 98765 43210",
        "+91-98765-43210",
        "09876543210",
        "919876543210",
        "0091 9876543210",
        "(98765) 43210",
    ],
)
def test_normalizes_common_formats(raw: str) -> None:
    assert normalize_indian_mobile(raw) == "+919876543210"


@pytest.mark.parametrize("raw", ["", "12345", "5876543210", "98765432101", "+1 9876543210", "98765abc10"])
def test_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValidationFailed):
        normalize_indian_mobile(raw)


def test_mask() -> None:
    assert mask_phone("+919876543210") == "98•••••210"


def test_tokens_are_bound_to_kind_and_id() -> None:
    s = make_settings()
    a, b = uuid.uuid4(), uuid.uuid4()
    t = make_token(s, "hold", a)
    assert verify_token(s, "hold", a, t)
    assert not verify_token(s, "hold", b, t)
    assert not verify_token(s, "booking", a, t)
    assert not verify_token(s, "hold", a, None)
    other = make_settings(jwt_secret="another-secret-0123456789-0123456789-xyz")
    assert not verify_token(other, "hold", a, t)


def test_reference_format() -> None:
    ref = new_reference("PLT")
    assert len(ref) == 10 and ref.startswith("PLT-") and not set(ref[4:]) & set("ILOU")
