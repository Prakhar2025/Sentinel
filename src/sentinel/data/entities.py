"""Synthetic identity entity builders.

All identifiers are generated from a seeded RNG with global uniqueness
tracking: nothing here is or derives from real PII. Phones use the Indian
mobile format, VPAs use real PSP domain suffixes with random local parts,
and collision with any specific real subscriber is statistically negligible
and never intentional.

Two RNGs are used deliberately: numpy's Generator for numeric distributions
(log-normal amounts, Zipf merchant draws) and Python's random.Random for
string population sampling, which keeps typing clean without Any-casts.
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable

PSP_DOMAINS = ["ybl", "okhdfcbank", "okaxis", "okicici", "paytm", "yapl", "ibl", "axl"]
EMAIL_DOMAINS = ["gmail.com", "yahoo.in", "outlook.com", "rediffmail.com"]
NAME_PARTS = [
    "aarav",
    "priya",
    "rahul",
    "ananya",
    "vikram",
    "sneha",
    "arjun",
    "kavya",
    "rohit",
    "isha",
    "aditya",
    "meera",
    "karan",
    "divya",
    "siddharth",
    "pooja",
    "varun",
    "nikita",
    "manav",
    "shruti",
    "dev",
    "anita",
    "yash",
    "riya",
    "nishant",
    "tanvi",
    "abhay",
    "sonal",
    "gaurav",
    "neha",
    "saurabh",
    "aarti",
    "mohit",
    "deepa",
    "rajat",
    "kalpana",
    "sameer",
    "lavanya",
    "harsh",
    "vaishali",
]

PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")
VPA_RE = re.compile(r"^[a-z0-9._-]+@[a-z]+$")


class EntityFactory:
    """Seeded, globally-unique synthetic identifier factory."""

    def __init__(self, rng: random.Random) -> None:
        self._rng = rng
        self._used_phones: set[str] = set()
        self._used_vpas: set[str] = set()
        self._used_devices: set[str] = set()
        self._used_customers: set[str] = set()
        self._used_emails: set[str] = set()

    def _fresh(self, used: set[str], build: Callable[[], str]) -> str:
        value = build()
        while value in used:
            value = build()
        used.add(value)
        return value

    def phone(self) -> str:
        """A fresh +91 mobile number in E.164 form."""

        def build() -> str:
            head = self._rng.choice("6789")
            rest = "".join(self._rng.choices("0123456789", k=9))
            return f"+91{head}{rest}"

        return self._fresh(self._used_phones, build)

    def vpa(self) -> str:
        """A fresh UPI VPA like priya482@okhdfcbank."""

        def build() -> str:
            name = self._rng.choice(NAME_PARTS)
            digits = self._rng.randint(1, 9999)
            sep = self._rng.choice(["", ".", "_"])
            domain = self._rng.choice(PSP_DOMAINS)
            return f"{name}{sep}{digits}@{domain}"

        return self._fresh(self._used_vpas, build)

    def device(self) -> str:
        """A fresh device fingerprint id."""

        def build() -> str:
            return "dev_" + "".join(self._rng.choices("0123456789abcdef", k=8))

        return self._fresh(self._used_devices, build)

    def customer(self) -> str:
        """A fresh customer id."""

        def build() -> str:
            return "cust_" + "".join(self._rng.choices("0123456789abcdef", k=6))

        return self._fresh(self._used_customers, build)

    def email(self, local: str | None = None) -> str:
        """A fresh email; optionally built around a given local part."""

        def build() -> str:
            if local is not None:
                return f"{local}@{self._rng.choice(EMAIL_DOMAINS)}"
            name = self._rng.choice(NAME_PARTS)
            surname = self._rng.choice(NAME_PARTS)
            digits = self._rng.randint(1, 999)
            form = self._rng.choice([f"{name}.{surname}", f"{name}{surname}"])
            return f"{form}{digits}@{self._rng.choice(EMAIL_DOMAINS)}"

        return self._fresh(self._used_emails, build)

    def ip(self) -> str:
        """A random (non-routable-by-construction-reserved-block) IPv4."""
        return f"103.{self._rng.randint(10, 99)}.{self._rng.randint(1, 254)}.{self._rng.randint(1, 254)}"

    def merchant_pool(self, size: int) -> list[str]:
        """A fixed pool of merchant ids, sampled in a stable order."""
        return [f"mcht_{i:05d}" for i in range(1, size + 1)]
