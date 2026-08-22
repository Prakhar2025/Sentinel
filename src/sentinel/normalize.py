"""Entity normalization for payment events (docs/04 data quality rules).

Deterministic, regex-based normalization only: no LLM, no network, no
side effects. Every normalizer returns None for values that cannot be
used for identity linking; the raw value is preserved separately for the
audit trail when the phone fails validation (doc 04: invalid phones are
stored as unnormalized and excluded from phone-linking).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

PHONE_NOISE = re.compile(r"[\s\-().]+")
PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")
VPA_RE = re.compile(r"^[a-z0-9._-]{1,64}@[a-z]{2,16}$")
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")

MAX_RAW_LENGTH = 128


def normalize_phone(raw: str | None) -> str | None:
    """Normalize an Indian mobile number to E.164 (+91XXXXXXXXXX).

    Accepts: +91 / 91 / 0 / bare-10-digit prefixes, and separators
    (spaces, dashes, dots, parentheses). Returns None when the value
    cannot be a valid Indian mobile number.
    """
    if not raw:
        return None
    digits = PHONE_NOISE.sub("", raw.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if not digits.isdigit():
        return None
    if len(digits) == 14 and digits.startswith("0091"):
        digits = digits[4:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10 or digits[0] not in "6789":
        return None
    normalized = f"+91{digits}"
    return normalized if PHONE_RE.match(normalized) else None


def normalize_vpa(raw: str | None) -> str | None:
    """Normalize a UPI VPA: trim and lowercase, validate the shape."""
    if not raw:
        return None
    value = raw.strip().lower()
    if len(value) > MAX_RAW_LENGTH:
        return None
    return value if VPA_RE.match(value) else None


def normalize_device_id(raw: str | None) -> str | None:
    """Normalize a device fingerprint id: trim, lowercase, bounded length."""
    if not raw:
        return None
    value = raw.strip().lower()
    if not value or len(value) > MAX_RAW_LENGTH:
        return None
    return value


def normalize_email(raw: str | None) -> str | None:
    """Normalize an email address: trim and lowercase, validate the shape."""
    if not raw:
        return None
    value = raw.strip().lower()
    if len(value) > MAX_RAW_LENGTH:
        return None
    return value if EMAIL_RE.match(value) else None


def normalize_ip(raw: str | None) -> str | None:
    """Normalize an IPv4 address, rejecting invalid octets."""
    if not raw:
        return None
    value = raw.strip()
    match = IPV4_RE.match(value)
    if not match:
        return None
    if any(int(octet) > 255 for octet in match.groups()):
        return None
    return value


class NormalizedEntities(BaseModel):
    """Normalized identity entities plus audit-only raw leftovers."""

    model_config = ConfigDict(extra="forbid")

    upi_vpa: str | None = None
    phone: str | None = None
    device_id: str | None = None
    email: str | None = None
    ip: str | None = None
    unnormalized_phone: str | None = None


def normalize_event_entities(
    upi_vpa: str | None,
    phone: str | None,
    device_id: str | None,
    email: str | None,
    ip: str | None,
) -> NormalizedEntities:
    """Normalize all identity fields of one event.

    When a phone fails validation its raw value is kept in
    unnormalized_phone for the audit trail but excluded from linking.
    """
    normalized_phone = normalize_phone(phone)
    return NormalizedEntities(
        upi_vpa=normalize_vpa(upi_vpa),
        phone=normalized_phone,
        device_id=normalize_device_id(device_id),
        email=normalize_email(email),
        ip=normalize_ip(ip),
        unnormalized_phone=None if normalized_phone is not None else phone,
    )
