"""Tests for entity normalization (docs/04 data quality rules)."""

from __future__ import annotations

import pytest

from sentinel.normalize import (
    normalize_device_id,
    normalize_email,
    normalize_event_entities,
    normalize_ip,
    normalize_phone,
    normalize_vpa,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+919812345678", "+919812345678"),
        ("919812345678", "+919812345678"),
        ("0091981234567 8".replace(" ", ""), "+919812345678"),
        ("09812345678", "+919812345678"),
        ("9812345678", "+919812345678"),
        ("+91 98123 45678", "+919812345678"),
        ("+91-98123-45678", "+919812345678"),
        ("(091) 9812345678".replace("091", "0"), "+919812345678"),
        ("  +918812345678  ", "+918812345678"),
        ("+916000000000", "+916000000000"),
        ("+917000000000", "+917000000000"),
        ("+919000000000", "+919000000000"),
    ],
)
def test_normalize_phone_valid(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "+915812345678",  # invalid leading digit (5)
        "981234567",  # too short
        "98123456789",  # 11 digits without prefix
        "abcdefghijk",
        "+9198123456789",  # too many digits
        "",
        None,
        "+91 12 45678",  # nonsense
    ],
)
def test_normalize_phone_invalid(raw: str | None) -> None:
    assert normalize_phone(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("User At Bank@ybl", None),  # spaces inside local part are invalid
        ("  priya482@okhdfcbank  ", "priya482@okhdfcbank"),
        ("PRIYA.482@YBL", "priya.482@ybl"),
        ("rahul-91_paytm@paytm", "rahul-91_paytm@paytm"),
        ("x@ybl", "x@ybl"),
    ],
)
def test_normalize_vpa(raw: str, expected: str | None) -> None:
    assert normalize_vpa(raw) == expected


def test_normalize_vpa_invalid() -> None:
    for bad in ("", None, "no-at-sign", "@ybl", "a@", "x" * 200 + "@ybl", "priya@ybl extra"):
        assert normalize_vpa(bad) is None


def test_normalize_device_and_email_and_ip() -> None:
    assert normalize_device_id("  DEV_9F2A1C ") == "dev_9f2a1c"
    assert normalize_device_id(None) is None
    assert normalize_device_id("x" * 200) is None
    assert normalize_email("  Priya.Sharma@GMAIL.com ") == "priya.sharma@gmail.com"
    assert normalize_email("not-an-email") is None
    assert normalize_ip("103.21.58.7") == "103.21.58.7"
    assert normalize_ip("103.21.58.999") is None
    assert normalize_ip("not-ip") is None
    assert normalize_ip(None) is None


def test_normalize_event_entities_happy_path() -> None:
    entities = normalize_event_entities(
        upi_vpa=" Priya@YBL ",
        phone="09812345678",
        device_id="DEV_01",
        email="A@B.com",
        ip="10.0.0.1",
    )
    assert entities.upi_vpa == "priya@ybl"
    assert entities.phone == "+919812345678"
    assert entities.device_id == "dev_01"
    assert entities.email == "a@b.com"
    assert entities.ip == "10.0.0.1"
    assert entities.unnormalized_phone is None


def test_normalize_event_entities_keeps_bad_phone_for_audit() -> None:
    entities = normalize_event_entities(
        upi_vpa="priya@ybl",
        phone="12345",
        device_id=None,
        email=None,
        ip=None,
    )
    assert entities.phone is None
    assert entities.unnormalized_phone == "12345"
